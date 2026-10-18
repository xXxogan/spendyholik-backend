"""Cross-cutting application ports (abstract interfaces).

Infrastructure provides concrete implementations; the application layer
depends only on these abstractions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from types import TracebackType
from uuid import UUID

from shared.domain.currency_code import CurrencyCode


class UnitOfWork(ABC):
    """Transactional boundary around one or more repository writes."""

    @abstractmethod
    def __enter__(self) -> UnitOfWork: ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class EmailGateway(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...


class PushGateway(ABC):
    @abstractmethod
    def send(self, user_id: UUID, title: str, body: str) -> None: ...


class ObjectStorage(ABC):
    """Storage for user uploads (receipts) and generated files (CSV export)."""

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def open(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class ExchangeRateProvider(ABC):
    @abstractmethod
    def get_rate(
        self, base: CurrencyCode, target: CurrencyCode, on: date | None = None
    ) -> Decimal | None:
        """Return the exchange rate (target per unit of base), or ``None``."""
