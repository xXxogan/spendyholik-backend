"""Domain entities for the debts bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

from debts.domain.enums import DebtDirection
from shared.domain.money import Money
from shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Debt:
    user_id: UUID
    person_name: str
    direction: DebtDirection
    amount: Money
    remaining: Money | None = None
    due_date: date | None = None
    is_closed: bool = False
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.person_name.strip():
            msg = "Debt person name must not be empty."
            raise ValidationError(msg)
        if not self.amount.is_positive():
            msg = "Debt amount must be positive."
            raise ValidationError(msg)
        if self.remaining is None:
            object.__setattr__(self, "remaining", self.amount)
        if self.remaining.currency != self.amount.currency:
            msg = "Debt remaining and amount must share a currency."
            raise ValidationError(msg)
        if self.remaining.is_negative():
            msg = "Debt remaining must be non-negative."
            raise ValidationError(msg)
        if self.is_closed and not self.remaining.is_zero():
            msg = "A closed debt must have zero remaining."
            raise ValidationError(msg)

    @property
    def paid_amount(self) -> Money:
        return self.amount - self.remaining


@dataclass(frozen=True, slots=True)
class DebtPayment:
    debt_id: UUID
    account_id: UUID
    amount: Money
    date: date
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.amount.is_positive():
            msg = "Debt payment amount must be positive."
            raise ValidationError(msg)
