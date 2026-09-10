"""Inclusive date-range value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            msg = f"DateRange end {self.end} precedes start {self.start}"
            raise ValidationError(msg)

    @property
    def days(self) -> int:
        """Number of days in the (inclusive) range."""
        return (self.end - self.start).days + 1

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end
