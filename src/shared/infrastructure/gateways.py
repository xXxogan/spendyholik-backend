"""Shared gateway implementations (email, push, storage, exchange rates)."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail

from shared.application.ports import EmailGateway, ExchangeRateProvider, ObjectStorage, PushGateway
from shared.domain.currency_code import CurrencyCode

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


class StubExchangeRateProvider(ExchangeRateProvider):
    """Returns pre-configured rates; swap for an external provider in production."""

    def __init__(self, rates: dict[tuple[str, str], Decimal] | None = None) -> None:
        self._rates = rates or {}

    def get_rate(
        self, base: CurrencyCode, target: CurrencyCode, on: date | None = None
    ) -> Decimal | None:
        return self._rates.get((base.value, target.value))
