"""Input/output DTOs for the debts application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from datetime import date as _date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from debts.domain.enums import DebtDirection, DebtEventKind
from finances.application.dto import AccountRefDTO
from shared.domain.money import Money


class CreateDebtInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_name: str = Field(min_length=1, max_length=120)
    direction: DebtDirection
    amount_minor: int = Field(gt=0)
    currency: str
    due_date: _date | None = None
    note: str = Field(default="", max_length=2000)
    #: The account the debt's money goes through: borrowed money comes in
    #: (``i_owe``), lent money goes out (``owed_to_me``). Without it the
    #: opening moves no balance.
    account_id: UUID | None = None
    #: Day of the opening; defaults to today.
    date: _date | None = None


class UpdateDebtInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_name: str | None = Field(default=None, min_length=1, max_length=120)
    #: New total; must not drop below what is already repaid (``below_repaid``).
    amount_minor: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)


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
    note: str
    created_at: datetime | None
    account_id: UUID | None = None
    opened_on: date | None = None


@dataclass(frozen=True, slots=True)
class DebtPaymentDTO:
    id: UUID
    debt_id: UUID
    account_id: UUID | None
    amount: Money
    date: date


@dataclass(frozen=True, slots=True)
class DebtEventDTO:
    """One line of a debt's history: its opening or a repayment."""

    id: UUID
    kind: DebtEventKind
    amount: Money
    date: date
    account: AccountRefDTO | None
