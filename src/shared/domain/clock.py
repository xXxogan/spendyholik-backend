"""Clock abstraction — the source of time, swappable in tests."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    """Port for obtaining the current time."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current UTC-aware datetime."""


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
