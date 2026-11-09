"""Celery tasks — thin wrappers over use cases."""

from __future__ import annotations

import csv
import io
import logging
import smtplib
from uuid import UUID

from celery import shared_task

from core.interfaces.deps import container
from finances.application.dto import ListTransactionsInput
from shared.exceptions import ExchangeRatesUnavailableError
from shared.infrastructure.gateways import DjangoEmailGateway

logger = logging.getLogger(__name__)


@shared_task(name="spendyholik.run_due_recurring", bind=True, max_retries=3)
def run_due_recurring(self) -> dict:
    result = container.run_due_recurring().execute()
    return {"generated": result.generated, "skipped": result.skipped}


@shared_task(
    name="spendyholik.send_email",
    # Connection problems are retried (smtplib errors are OSError); a refused
    # recipient or sender is permanent. 30 + 60 + 120 s stays inside a code's 15 min.
    autoretry_for=(OSError,),
    dont_autoretry_for=(smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused),
    retry_backoff=30,
    retry_backoff_max=120,
    retry_jitter=False,
    max_retries=3,
)
def send_email(to: str, subject: str, body: str) -> None:
    DjangoEmailGateway().send(to, subject, body)


@shared_task(
    name="spendyholik.refresh_exchange_rates",
    autoretry_for=(ExchangeRatesUnavailableError,),
    retry_backoff=60,
    max_retries=5,
)
def refresh_exchange_rates() -> dict:
    return {"updated": container.refresh_exchange_rates().execute()}


@shared_task(name="spendyholik.send_weekly_report")
def send_weekly_report() -> dict:
    logger.info("Weekly report generation is not yet wired to a summary gateway.")
    return {"sent": 0}


@shared_task(name="spendyholik.notify_upcoming_recurring")
def notify_upcoming_recurring() -> dict:
    return {"notified": container.notify_upcoming_recurring().execute()}


@shared_task(name="spendyholik.generate_csv_export")
def generate_csv_export(user_id: str) -> str:
    """Generate a CSV of the user's transactions and store it in object storage."""
    from shared.infrastructure.gateways import FileSystemObjectStorage

    uid = UUID(user_id)
    list_transactions = container.list_transactions()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "type", "amount_minor", "currency", "date", "note", "account_id", "category_id"]
    )
    cursor: str | None = None
    while True:
        page = list_transactions.execute(uid, ListTransactionsInput(limit=100, cursor=cursor))
        for t in page.items:
            writer.writerow(
                [
                    str(t.id),
                    t.type.value,
                    t.amount.to_minor_units(),
                    t.amount.currency,
                    t.date.isoformat(),
                    t.note,
                    t.account_id,
                    t.category_id,
                ]
            )
        cursor = page.next_cursor
        if cursor is None:
            break
    key = f"exports/{uid}/transactions.csv"
    FileSystemObjectStorage().save(key, buf.getvalue().encode("utf-8"), "text/csv")
    return key
