"""Ports (abstract interfaces) for the finances bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection
from datetime import date
from decimal import Decimal
from uuid import UUID

from finances.application.dto import FeedPageDTO, TransactionLabels
from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import Granularity, TransactionType
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money

#: Amounts keyed by ISO 4217 currency code.
type CurrencyTotals = dict[str, Money]


class AccountRepository(ABC):
    @abstractmethod
    def add(self, account: Account) -> Account: ...

    @abstractmethod
    def get_by_id(self, account_id: UUID, user_id: UUID) -> Account | None: ...

    @abstractmethod
    def list_for_user(self, user_id: UUID, *, include_archived: bool = False) -> list[Account]: ...

    @abstractmethod
    def update(self, account: Account) -> Account: ...

    @abstractmethod
    def delete(self, account_id: UUID, user_id: UUID) -> bool:
        """Delete the user\'s entity; ``False`` if it did not exist."""


class CategoryRepository(ABC):
    @abstractmethod
    def add(self, category: Category) -> Category: ...

    @abstractmethod
    def get_by_id(self, category_id: UUID, user_id: UUID) -> Category | None: ...

    @abstractmethod
    def list_for_user(self, user_id: UUID) -> list[Category]: ...

    @abstractmethod
    def update(self, category: Category) -> Category: ...

    @abstractmethod
    def delete(self, category_id: UUID, user_id: UUID) -> bool:
        """Delete the user\'s entity; ``False`` if it did not exist."""

    @abstractmethod
    def is_ancestor(self, user_id: UUID, ancestor_id: UUID, descendant_id: UUID) -> bool: ...

    @abstractmethod
    def has_transactions(self, category_id: UUID, user_id: UUID) -> bool: ...

    @abstractmethod
    def has_budgets(self, category_id: UUID, user_id: UUID) -> bool: ...

    @abstractmethod
    def transaction_counts(self, user_id: UUID) -> dict[UUID, int]:
        """Number of transactions per category (direct, not including subcategories)."""


class TransactionRepository(ABC):
    @abstractmethod
    def add(self, transaction: Transaction) -> Transaction: ...

    @abstractmethod
    def get_by_id(self, transaction_id: UUID, user_id: UUID) -> Transaction | None: ...

    @abstractmethod
    def get_labeled(
        self, transaction_id: UUID, user_id: UUID
    ) -> tuple[Transaction, TransactionLabels] | None: ...

    @abstractmethod
    def update(self, transaction: Transaction) -> Transaction: ...

    @abstractmethod
    def delete(self, transaction_id: UUID, user_id: UUID) -> bool:
        """Delete the user\'s entity; ``False`` if it did not exist."""

    @abstractmethod
    def list_for_user(
        self,
        user_id: UUID,
        *,
        account_id: UUID | None = None,
        category_id: UUID | None = None,
        type: TransactionType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[tuple[Transaction, TransactionLabels]], str | None]:
        """A page ordered newest first (date, then creation) and the next cursor.

        ``account_id`` matches the source account and the destination of a
        transfer; ``category_id`` matches the category and all of its
        subcategories; ``search`` looks in the title and the note.
        """

    @abstractmethod
    def exists_for_source(self, user_id: UUID, recurring_id: UUID, date: date) -> bool: ...

    # Aggregates skip archived accounts and are grouped by currency, because a
    # user's accounts may be denominated in different currencies.
    @abstractmethod
    def totals_by_type(
        self,
        user_id: UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[TransactionType, CurrencyTotals]: ...

    @abstractmethod
    def sum_by_category(
        self,
        user_id: UUID,
        *,
        type: TransactionType,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[UUID, CurrencyTotals]: ...

    @abstractmethod
    def monthly_totals(
        self,
        user_id: UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[tuple[date, TransactionType], CurrencyTotals]:
        """Totals keyed by (first day of month, transaction type)."""

    @abstractmethod
    def period_totals(
        self,
        user_id: UUID,
        *,
        granularity: Granularity,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[tuple[date, TransactionType], CurrencyTotals]:
        """Totals keyed by (first day of the day/month/year bucket, transaction type)."""


class BudgetRepository(ABC):
    @abstractmethod
    def add(self, budget: Budget) -> Budget: ...

    @abstractmethod
    def get_by_id(self, budget_id: UUID, user_id: UUID) -> Budget | None: ...

    @abstractmethod
    def list_for_user(self, user_id: UUID) -> list[Budget]: ...

    @abstractmethod
    def update(self, budget: Budget) -> Budget: ...

    @abstractmethod
    def delete(self, budget_id: UUID, user_id: UUID) -> bool:
        """Delete the user\'s entity; ``False`` if it did not exist."""

    @abstractmethod
    def exists_for_category(
        self, user_id: UUID, category_id: UUID, *, exclude_id: UUID | None = None
    ) -> bool: ...


class BalanceReader(ABC):
    """Account balance movements from every source.

    Transactions (income, expense, both legs of a transfer), goal contributions
    (money leaves the account) and debt repayments (``i_owe`` leaves the
    account, ``owed_to_me`` comes in) all move a balance. A balance is the
    account's initial balance plus its delta.
    """

    @abstractmethod
    def deltas(
        self,
        user_id: UUID,
        account_ids: Collection[UUID] | None = None,
        *,
        before: date | None = None,
    ) -> dict[UUID, Decimal]:
        """Net movement per account (accounts without movements are omitted).

        With ``before``, only movements dated strictly before that day count.
        """

    @abstractmethod
    def daily_deltas(
        self, user_id: UUID, account_id: UUID, date_from: date, date_to: date
    ) -> dict[date, Decimal]:
        """Net movement of one account per day within ``[date_from, date_to]``."""


class TransactionObserver(ABC):
    """Told after a transaction is created, changed or deleted (e.g. to notify).

    Implementations must not raise: a failed side effect never undoes the write.
    """

    @abstractmethod
    def changed(
        self, user_id: UUID, before: Transaction | None, after: Transaction | None
    ) -> None: ...


class FeedReader(ABC):
    """Transactions together with the goal and debt events that move balances."""

    @abstractmethod
    def page(
        self,
        user_id: UUID,
        *,
        account_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> FeedPageDTO:
        """Newest first by (date, creation, id), with one shared cursor."""


class ExchangeRateRepository(ABC):
    @abstractmethod
    def add(self, rate: ExchangeRate) -> ExchangeRate: ...

    @abstractmethod
    def get_latest(self, base: CurrencyCode, target: CurrencyCode) -> ExchangeRate | None: ...

    @abstractmethod
    def save_many(self, rates: list[ExchangeRate]) -> int:
        """Insert or replace rates (one per base, target and date); returns how many."""
