"""Domain entities for the finances bounded context (accounts, categories,
transactions, budgets, exchange rates)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from finances.domain.enums import AccountType, BudgetPeriod, TransactionType
from finances.domain.value_objects import CategoryColor
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money
from shared.exceptions import ValidationError


def _require_money_currency(money: Money, currency: CurrencyCode) -> None:
    if money.currency != currency.value:
        msg = f"Money currency {money.currency} does not match account currency {currency.value}"
        raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class Account:
    user_id: UUID
    name: str
    type: AccountType
    currency: CurrencyCode
    initial_balance: Money | None = None  # defaults to zero in the account's currency
    color: CategoryColor = CategoryColor("default")
    last4: str | None = None
    credit_limit: Money | None = None
    interest_rate: Decimal = Decimal("0")
    is_archived: bool = False
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "Account name must not be empty."
            raise ValidationError(msg)
        if self.initial_balance is None:
            object.__setattr__(self, "initial_balance", Money.zero(self.currency.value))
        _require_money_currency(self.initial_balance, self.currency)
        if self.credit_limit is not None:
            _require_money_currency(self.credit_limit, self.currency)
            if self.credit_limit.is_negative():
                msg = "Credit limit must be non-negative."
                raise ValidationError(msg)
        if self.last4 is not None and not (self.last4.isdigit() and len(self.last4) <= 4):
            msg = "last4 must be a string of at most 4 digits."
            raise ValidationError(msg)
        if self.interest_rate < 0:
            msg = "Interest rate must be non-negative."
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class Category:
    user_id: UUID
    name: str
    type: TransactionType
    icon: str = "tag"
    color: CategoryColor = CategoryColor("default")
    parent_id: UUID | None = None
    is_system: bool = False
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "Category name must not be empty."
            raise ValidationError(msg)
        if self.parent_id is not None and self.parent_id == self.id:
            msg = "Category cannot be its own parent."
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class Transaction:
    user_id: UUID
    account_id: UUID
    type: TransactionType
    amount: Money
    date: date
    category_id: UUID | None = None
    time: time | None = None
    note: str = ""
    #: Name the user gave; empty means "render the category (or account) name".
    title: str = ""
    receipt_id: UUID | None = None
    transfer_to_account_id: UUID | None = None
    recurring_source_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.type is TransactionType.TRANSFER:
            if self.transfer_to_account_id is None:
                msg = "A transfer requires a destination account."
                raise ValidationError(msg)
            if self.transfer_to_account_id == self.account_id:
                msg = "A transfer requires two distinct accounts."
                raise ValidationError(msg)
        elif self.transfer_to_account_id is not None:
            msg = "transfer_to_account_id is only allowed for transfers."
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class Budget:
    user_id: UUID
    category_id: UUID
    amount: Money
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    start_date: date | None = None
    #: Last day of a ``one_time`` budget (inclusive); unused by recurring periods.
    end_date: date | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.amount.is_positive():
            msg = "Budget amount must be positive."
            raise ValidationError(msg)
        if self.start_date and self.end_date and self.end_date < self.start_date:
            msg = "Budget end date must not precede its start date."
            raise ValidationError(msg, field="end_date")

    def period_bounds(self, today: date) -> tuple[date | None, date | None]:
        """First and last day (inclusive) of the period containing ``today``.

        ``None`` means unbounded — only for a ``one_time`` budget without dates.
        """
        if self.period is BudgetPeriod.WEEKLY:
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if self.period is BudgetPeriod.ONE_TIME:
            return self.start_date, self.end_date
        start = today.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    base: CurrencyCode
    target: CurrencyCode
    rate: Decimal
    date: date
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.base == self.target:
            msg = "Exchange rate base and target must differ."
            raise ValidationError(msg)
        if self.rate <= 0:
            msg = "Exchange rate must be positive."
            raise ValidationError(msg)
