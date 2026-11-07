"""Input/output DTOs for the finances application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import time as _time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finances.domain.enums import AccountType, BudgetPeriod, TransactionType
from shared.domain.money import Money


# ---------------------------------------------------------------------------
# Input DTOs (pydantic)
# ---------------------------------------------------------------------------
class CreateAccountInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    type: AccountType
    currency: str
    initial_balance_minor: int = 0
    color: str = "default"
    last4: str | None = None
    credit_limit_minor: int | None = None
    interest_rate: Decimal = Decimal("0")


class UpdateAccountInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: AccountType | None = None
    color: str | None = None
    last4: str | None = None
    credit_limit_minor: int | None = None
    interest_rate: Decimal | None = None


class CreateCategoryInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    type: TransactionType
    icon: str = "tag"
    color: str = "default"
    parent_id: UUID | None = None


class UpdateCategoryInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = None
    color: str | None = None
    parent_id: UUID | None = None


class CreateTransactionInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: UUID
    type: TransactionType
    amount_minor: int = Field(gt=0)
    date: _date
    category_id: UUID | None = None
    time: _time | None = None
    note: str = Field(default="", max_length=2000)
    transfer_to_account_id: UUID | None = None


class UpdateTransactionInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: UUID | None = None
    category_id: UUID | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    date: _date | None = None
    time: _time | None = None
    note: str | None = None
    transfer_to_account_id: UUID | None = None


class ListTransactionsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: UUID | None = None
    category_id: UUID | None = None
    type: TransactionType | None = None
    date_from: _date | None = None
    date_to: _date | None = None
    search: str | None = None
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class CreateBudgetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    category_id: UUID
    amount_minor: int = Field(gt=0)
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    start_date: _date | None = None
    is_active: bool = True


class UpdateBudgetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    category_id: UUID | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    period: BudgetPeriod | None = None
    start_date: _date | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Output DTOs (dataclasses)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AccountDTO:
    id: UUID
    name: str
    type: AccountType
    currency: str
    initial_balance: Money
    color: str
    last4: str | None
    credit_limit: Money | None
    interest_rate: Decimal
    is_archived: bool


@dataclass(frozen=True, slots=True)
class CategoryDTO:
    id: UUID
    name: str
    type: TransactionType
    icon: str
    color: str
    parent_id: UUID | None
    is_system: bool


@dataclass(frozen=True, slots=True)
class TransactionLabels:
    """Display data of a transaction's account/category, loaded in the same query."""

    account_name: str
    category_name: str | None = None
    category_icon: str | None = None
    category_color: str | None = None


@dataclass(frozen=True, slots=True)
class TransactionDTO:
    id: UUID
    account_id: UUID
    category_id: UUID | None
    type: TransactionType
    amount: Money
    date: _date
    time: _time | None
    note: str
    receipt_id: UUID | None
    transfer_to_account_id: UUID | None
    labels: TransactionLabels | None = None


@dataclass(frozen=True, slots=True)
class TransactionPageDTO:
    items: list[TransactionDTO]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class BudgetDTO:
    id: UUID
    category_id: UUID
    amount: Money
    period: BudgetPeriod
    start_date: _date | None
    is_active: bool
