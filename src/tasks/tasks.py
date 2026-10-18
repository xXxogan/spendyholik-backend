"""Celery tasks — thin wrappers over use cases."""

from __future__ import annotations

import csv
import io
import logging
from uuid import UUID

from celery import shared_task

from core.interfaces.deps import container
from finances.application.dto import ListTransactionsInput

logger = logging.getLogger(__name__)


@shared_task(name="spendyholik.run_due_recurring", bind=True, max_retries=3)
def run_due_recurring(self) -> dict:
    result = container.run_due_recurring().execute()
    return {"generated": result.generated, "skipped": result.skipped}


@shared_task(name="spendyholik.refresh_exchange_rates")
def refresh_exchange_rates() -> dict:
    # Uses the exchange-rate provider; swaps to an external API in production.
    from shared.infrastructure.gateways import StubExchangeRateProvider

    provider = StubExchangeRateProvider()
    # The reference implementation relies on a configured provider; no-op here.
    _ = provider
    return {"updated": 0}


@shared_task(name="spendyholik.send_weekly_report")
def send_weekly_report() -> dict:
    logger.info("Weekly report generation is not yet wired to a summary gateway.")
    return {"sent": 0}


@shared_task(name="spendyholik.notify_upcoming_recurring")
def notify_upcoming_recurring() -> dict:
    logger.info("Upcoming-recurring reminders are not yet wired to push/email.")
    return {"notified": 0}


@shared_task(name="spendyholik.generate_csv_export")
def generate_csv_export(user_id: str) -> str:
    """Generate a CSV of the user's transactions and store it in object storage."""
    from shared.infrastructure.gateways import FileSystemObjectStorage

    uid = UUID(user_id)
    transactions, _ = container.list_transactions().execute(uid, ListTransactionsInput(limit=1000))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "type", "amount_minor", "currency", "date", "note", "account_id", "category_id"]
    )
    for t in transactions:
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
    key = f"exports/{uid}/transactions.csv"
    FileSystemObjectStorage().save(key, buf.getvalue().encode("utf-8"), "text/csv")
    return key
