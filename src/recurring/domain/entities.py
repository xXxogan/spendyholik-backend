"""Domain entities for the recurring bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

from finances.domain.enums import TransactionType
from recurring.domain.enums import RecurringFrequency
from shared.domain.money import Money
from shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class RecurringTransaction:
    user_id: UUID
    name: str
    amount: Money
    type: TransactionType
    account_id: UUID
    frequency: RecurringFrequency
    next_run: date
    category_id: UUID | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "Recurring transaction name must not be empty."
            raise ValidationError(msg)
        if self.amount.is_zero():
            msg = "Recurring transaction amount must be non-zero."
            raise ValidationError(msg)
