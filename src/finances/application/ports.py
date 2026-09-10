"""Ports (abstract interfaces) for the finances bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import TransactionType
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money


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
    def delete(self, account_id: UUID, user_id: UUID) -> None: ...


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
    def delete(self, category_id: UUID, user_id: UUID) -> None: ...

    @abstractmethod
    def is_ancestor(self, user_id: UUID, ancestor_id: UUID, descendant_id: UUID) -> bool: ...

    @abstractmethod
    def has_transactions(self, category_id: UUID, user_id: UUID) -> bool: ...


class TransactionRepository(ABC):
    @abstractmethod
    def add(self, transaction: Transaction) -> Transaction: ...

    @abstractmethod
    def get_by_id(self, transaction_id: UUID, user_id: UUID) -> Transaction | None: ...

    @abstractmethod
    def update(self, transaction: Transaction) -> Transaction: ...

    @abstractmethod
    def delete(self, transaction_id: UUID, user_id: UUID) -> None: ...

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
    ) -> tuple[list[Transaction], str | None]: ...

    @abstractmethod
    def exists_for_source(self, user_id: UUID, recurring_id: UUID, date: date) -> bool: ...

    @abstractmethod
    def total_amount(
        self,
        user_id: UUID,
        *,
        type: TransactionType | None = None,
        account_id: UUID | None = None,
        category_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Money: ...

    @abstractmethod
    def sum_by_category(
        self,
        user_id: UUID,
        *,
        type: TransactionType,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[UUID, Money]: ...

    @abstractmethod
    def monthly_totals(
        self,
        user_id: UUID,
        *,
        type: TransactionType,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[tuple[date, Money]]: ...


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
    def delete(self, budget_id: UUID, user_id: UUID) -> None: ...


class ExchangeRateRepository(ABC):
    @abstractmethod
    def add(self, rate: ExchangeRate) -> ExchangeRate: ...

    @abstractmethod
    def get_latest(self, base: CurrencyCode, target: CurrencyCode) -> ExchangeRate | None: ...
