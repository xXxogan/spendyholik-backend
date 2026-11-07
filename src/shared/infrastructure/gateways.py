"""Shared gateway implementations (email, push, storage, exchange rates)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail

from shared.application.ports import (
    EmailGateway,
    ExchangeRateProvider,
    ObjectStorage,
    PushGateway,
    RatesSnapshot,
)
from shared.domain.currency_code import CurrencyCode
from shared.exceptions import DomainError, ExchangeRatesUnavailableError

logger = logging.getLogger(__name__)


class DjangoEmailGateway(EmailGateway):
    def send(self, to: str, subject: str, body: str) -> None:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)


class LoggingPushGateway(PushGateway):
    """Fallback push gateway that logs instead of hitting FCM/APNs."""

    def send(self, user_id: UUID, title: str, body: str) -> None:
        logger.info("push to %s: %s — %s", user_id, title, body)


class FileSystemObjectStorage(ObjectStorage):
    """Stores blobs under ``MEDIA_ROOT`` (local PVC in production)."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(settings.MEDIA_ROOT)

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def open(self, key: str) -> bytes:
        return (self._root / key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._root / key
        if path.exists():
            path.unlink()


class OpenErApiExchangeRateProvider(ExchangeRateProvider):
    """Daily rates from ExchangeRate-API's open endpoint (no key; ~160 currencies, RUB too).

    ``EXCHANGE_RATES_URL`` holds the endpoint with a ``{base}`` placeholder.
    The open endpoint asks for attribution: "Rates By Exchange Rate API".
    """

    def __init__(self, url: str | None = None, timeout: float = 10.0) -> None:
        self._url = url or settings.EXCHANGE_RATES_URL
        self._timeout = timeout

    def latest(self, base: CurrencyCode) -> RatesSnapshot:
        request = Request(
            self._url.format(base=base.value), headers={"User-Agent": "spendyholik-backend"}
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read())
        except (URLError, TimeoutError, ValueError) as exc:
            raise ExchangeRatesUnavailableError(str(exc)) from exc
        return parse_open_er_api(payload, base.value)


def parse_open_er_api(payload: dict, base: str) -> RatesSnapshot:
    """Turn an open.er-api.com ``/latest`` answer into a snapshot (bad entries skipped)."""
    if payload.get("result") != "success" or payload.get("base_code") != base:
        msg = f"Unexpected exchange-rate answer: {payload.get('result')!r}"
        raise ExchangeRatesUnavailableError(msg)
    rates: dict[str, Decimal] = {}
    for code, value in (payload.get("rates") or {}).items():
        try:
            rate = Decimal(str(value))
            currency = CurrencyCode(code).value
        except InvalidOperation, DomainError:  # skip junk entries
            continue
        if rate > 0 and currency != base:
            rates[currency] = rate
    updated = payload.get("time_last_update_unix")
    day = datetime.fromtimestamp(updated, tz=UTC).date() if updated else datetime.now(UTC).date()
    return RatesSnapshot(base=base, date=day, rates=rates)
