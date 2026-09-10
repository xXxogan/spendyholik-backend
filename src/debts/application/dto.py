"""Input/output DTOs for the debts application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from debts.domain.enums import DebtDirection
from shared.domain.money import Money


class CreateDebtInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_name: str = Field(min_length=1, max_length=120)
    direction: DebtDirection
    amount_minor: int = Field(gt=0)
    currency: str
    due_date: date | None = None


class UpdateDebtInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_name: str | None = Field(default=None, min_length=1, max_length=120)
    due_date: date | None = None


class RepayDebtInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: UUID
    amount_minor: int = Field(gt=0)
    date: date


@dataclass(frozen=True, slots=True)
class DebtDTO:
    id: UUID
    person_name: str
    direction: DebtDirection
    amount: Money
    remaining: Money
    due_date: date | None
    is_closed: bool


@dataclass(frozen=True, slots=True)
class DebtPaymentDTO:
    id: UUID
    debt_id: UUID
    account_id: UUID
    amount: Money
    date: date
