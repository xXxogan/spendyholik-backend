"""Domain entities for the goals bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

from shared.domain.money import Money
from shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Goal:
    user_id: UUID
    name: str
    target_amount: Money
    #: Account the goal was opened with; contributions name their own account.
    account_id: UUID | None = None
    initial_amount: Money = field(default_factory=lambda: Money.zero("RUB"))
    deadline: date | None = None
    icon: str = "flag"
    color: str = "goal"
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "Goal name must not be empty."
            raise ValidationError(msg)
        if not self.target_amount.is_positive():
            msg = "Goal target amount must be positive."
            raise ValidationError(msg)
        if self.initial_amount.is_negative():
            msg = "Goal initial amount must be non-negative."
            raise ValidationError(msg)
        if self.initial_amount.currency != self.target_amount.currency:
            msg = "Goal initial and target amounts must share a currency."
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class GoalContribution:
    goal_id: UUID
    account_id: UUID | None  # None once the account is deleted
    amount: Money
    date: date
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.amount.is_positive():
            msg = "Goal contribution amount must be positive."
            raise ValidationError(msg)
