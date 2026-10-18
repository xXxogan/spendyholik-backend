"""Input/output DTOs for the recurring application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finances.domain.enums import TransactionType
from recurring.domain.enums import RecurringFrequency
from shared.domain.money import Money


class CreateRecurringInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    amount_minor: int
    type: TransactionType
    account_id: UUID
    frequency: RecurringFrequency
    next_run: date
    category_id: UUID | None = None
    is_active: bool = True


class UpdateRecurringInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    amount_minor: int | None = None
    account_id: UUID | None = None
    category_id: UUID | None = None
    frequency: RecurringFrequency | None = None
    next_run: date | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class RecurringDTO:
    id: UUID
    name: str
    amount: Money
    type: TransactionType
    account_id: UUID
    category_id: UUID | None
    frequency: RecurringFrequency
    next_run: date
    is_active: bool


@dataclass(frozen=True, slots=True)
class RunDueRecurringResultDTO:
    generated: int
    skipped: int


class ToggleRecurringInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_active: bool = True
