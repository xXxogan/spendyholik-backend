"""Use cases for the finances bounded context (accounts, categories,
transactions, budgets)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from accounts.application.ports import ProfileRepository
from finances.application.dto import (
    AccountDTO,
    BudgetDTO,
    CategoryDTO,
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
    ListTransactionsInput,
    TransactionDTO,
    TransactionLabels,
    TransactionPageDTO,
    UpdateAccountInput,
    UpdateBudgetInput,
    UpdateCategoryInput,
    UpdateTransactionInput,
)
from finances.application.ports import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)
from finances.domain.entities import Account, Budget, Category, Transaction
from finances.domain.enums import TransactionType
from finances.domain.exceptions import (
    AccountArchivedError,
    AccountNotFoundError,
    BudgetNotFoundError,
    CategoryCycleError,
    CategoryInUseError,
    CategoryNotFoundError,
    TransactionNotFoundError,
)
from finances.domain.value_objects import CategoryColor
from shared.application.patch import apply_patch
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import DEFAULT_CURRENCY, Money
from shared.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Mappers (domain entity → output DTO)
# ---------------------------------------------------------------------------
def _account_dto(a: Account) -> AccountDTO:
    return AccountDTO(
        id=a.id,
        name=a.name,
        type=a.type,
        currency=a.currency.value,
        initial_balance=a.initial_balance,
        color=a.color.value,
        last4=a.last4,
        credit_limit=a.credit_limit,
        interest_rate=a.interest_rate,
        is_archived=a.is_archived,
    )


def _category_dto(c: Category) -> CategoryDTO:
    return CategoryDTO(
        id=c.id,
        name=c.name,
        type=c.type,
        icon=c.icon,
        color=c.color.value,
        parent_id=c.parent_id,
        is_system=c.is_system,
    )


def _transaction_dto(t: Transaction, labels: TransactionLabels | None = None) -> TransactionDTO:
    return TransactionDTO(
        id=t.id,
        account_id=t.account_id,
        category_id=t.category_id,
        type=t.type,
        amount=t.amount,
        date=t.date,
        time=t.time,
        note=t.note,
        receipt_id=t.receipt_id,
        transfer_to_account_id=t.transfer_to_account_id,
        labels=labels,
    )


def _budget_dto(b: Budget) -> BudgetDTO:
    return BudgetDTO(
        id=b.id,
        category_id=b.category_id,
        amount=b.amount,
        period=b.period,
        start_date=b.start_date,
        is_active=b.is_active,
    )


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
class CreateAccount:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, data: CreateAccountInput) -> AccountDTO:
        currency = CurrencyCode(data.currency)
        account = Account(
            user_id=user_id,
            name=data.name,
            type=data.type,
            currency=currency,
            initial_balance=Money.from_minor_units(data.initial_balance_minor, data.currency),
            color=CategoryColor(data.color),
            last4=data.last4,
            credit_limit=(
                Money.from_minor_units(data.credit_limit_minor, data.currency)
                if data.credit_limit_minor is not None
                else None
            ),
            interest_rate=data.interest_rate,
        )
        return _account_dto(self._accounts.add(account))


class UpdateAccount:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, account_id: UUID, data: UpdateAccountInput) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        currency = account.currency.value
        updated = apply_patch(
            account,
            data,
            fields={
                "color": ("color", CategoryColor),
                "credit_limit_minor": (
                    "credit_limit",
                    lambda minor: Money.from_minor_units(minor, currency),
                ),
            },
            nullable={"last4", "credit_limit_minor"},
        )
        return _account_dto(self._accounts.update(updated))


class ArchiveAccount:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, account_id: UUID) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        return _account_dto(self._accounts.update(replace(account, is_archived=True)))


class ListAccounts:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, *, include_archived: bool = False) -> list[AccountDTO]:
        accounts = self._accounts.list_for_user(user_id, include_archived=include_archived)
        return [_account_dto(a) for a in accounts]


class GetAccountDetail:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, account_id: UUID) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        return _account_dto(account)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
class ListCategories:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID) -> list[CategoryDTO]:
        return [_category_dto(c) for c in self._categories.list_for_user(user_id)]


class CreateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID, data: CreateCategoryInput) -> CategoryDTO:
        if data.parent_id is not None:
            parent = self._categories.get_by_id(data.parent_id, user_id)
            if parent is None:
                raise CategoryNotFoundError(data.parent_id)
        category = Category(
            user_id=user_id,
            name=data.name,
            type=data.type,
            icon=data.icon,
            color=CategoryColor(data.color),
            parent_id=data.parent_id,
        )
        return _category_dto(self._categories.add(category))


class UpdateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID, category_id: UUID, data: UpdateCategoryInput) -> CategoryDTO:
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if category.is_system:
            raise CategoryInUseError("System categories are read-only.")
        if data.parent_id is not None and data.parent_id != category.parent_id:
            if data.parent_id == category_id:
                raise CategoryCycleError
            if self._categories.get_by_id(data.parent_id, user_id) is None:
                raise CategoryNotFoundError(data.parent_id)
            if self._categories.is_ancestor(user_id, category_id, data.parent_id):
                raise CategoryCycleError
        updated = apply_patch(
            category, data, fields={"color": ("color", CategoryColor)}, nullable={"parent_id"}
        )
        return _category_dto(self._categories.update(updated))


class DeleteCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID, category_id: UUID) -> None:
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if category.is_system:
            raise CategoryInUseError("System categories cannot be deleted.")
        if self._categories.has_transactions(category_id, user_id):
            raise CategoryInUseError
        self._categories.delete(category_id, user_id)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class _TransactionGuard:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._accounts = accounts
        self._categories = categories
        self._transactions = transactions

    def _require_account(
        self, user_id: UUID, account_id: UUID, *, allow_archived: bool = False
    ) -> Account:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        if account.is_archived and not allow_archived:
            raise AccountArchivedError
        return account

    def _require_category(
        self, user_id: UUID, category_id: UUID | None, tx_type: TransactionType
    ) -> None:
        if category_id is None:
            return
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if (
            tx_type in (TransactionType.EXPENSE, TransactionType.INCOME)
            and category.type != tx_type
        ):
            msg = (
                f"Category type {category.type.value} does not match "
                f"transaction type {tx_type.value}."
            )
            raise ValidationError(msg)

    def validate(
        self,
        user_id: UUID,
        *,
        account_id: UUID,
        tx_type: TransactionType,
        category_id: UUID | None,
        transfer_to_account_id: UUID | None,
    ) -> Account:
        """Check references and return the (source) account."""
        account = self._require_account(user_id, account_id)
        if tx_type is TransactionType.TRANSFER and transfer_to_account_id not in (None, account_id):
            dest = self._require_account(user_id, transfer_to_account_id)
            if dest.currency != account.currency:
                msg = "Cross-currency transfers are not supported yet."
                raise ValidationError(msg)
        # A missing or identical destination is rejected by the Transaction entity.
        self._require_category(user_id, category_id, tx_type)
        return account


class CreateTransaction:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._guard = _TransactionGuard(accounts, categories, transactions)
        self._transactions = transactions

    def execute(self, user_id: UUID, data: CreateTransactionInput) -> TransactionDTO:
        account = self._guard.validate(
            user_id,
            account_id=data.account_id,
            tx_type=data.type,
            category_id=data.category_id,
            transfer_to_account_id=data.transfer_to_account_id,
        )
        transaction = Transaction(
            user_id=user_id,
            account_id=data.account_id,
            category_id=data.category_id,
            type=data.type,
            amount=Money.from_minor_units(data.amount_minor, account.currency.value),
            date=data.date,
            time=data.time,
            note=data.note,
            transfer_to_account_id=data.transfer_to_account_id,
        )
        return _transaction_dto(self._transactions.add(transaction))


class GetTransaction:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, transaction_id: UUID) -> TransactionDTO:
        found = self._transactions.get_labeled(transaction_id, user_id)
        if found is None:
            raise TransactionNotFoundError(transaction_id)
        return _transaction_dto(*found)


class UpdateTransaction:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._guard = _TransactionGuard(accounts, categories, transactions)
        self._transactions = transactions

    def execute(
        self, user_id: UUID, transaction_id: UUID, data: UpdateTransactionInput
    ) -> TransactionDTO:
        tx = self._transactions.get_by_id(transaction_id, user_id)
        if tx is None:
            raise TransactionNotFoundError(transaction_id)
        # The amount is re-denominated below, once the (possibly new) account is known.
        draft = apply_patch(
            tx,
            data,
            fields={"amount_minor": ("amount", lambda _: tx.amount)},
            nullable={"category_id", "time", "transfer_to_account_id"},
        )
        account = self._guard.validate(
            user_id,
            account_id=draft.account_id,
            tx_type=draft.type,
            category_id=draft.category_id,
            transfer_to_account_id=draft.transfer_to_account_id,
        )
        minor = tx.amount.to_minor_units() if data.amount_minor is None else data.amount_minor
        updated = replace(draft, amount=Money.from_minor_units(minor, account.currency.value))
        return _transaction_dto(self._transactions.update(updated))


class DeleteTransaction:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, transaction_id: UUID) -> None:
        if not self._transactions.delete(transaction_id, user_id):
            raise TransactionNotFoundError(transaction_id)


class ListTransactions:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, data: ListTransactionsInput) -> TransactionPageDTO:
        items, next_cursor = self._transactions.list_for_user(
            user_id,
            account_id=data.account_id,
            category_id=data.category_id,
            type=data.type,
            date_from=data.date_from,
            date_to=data.date_to,
            search=data.search,
            cursor=data.cursor,
            limit=data.limit,
        )
        return TransactionPageDTO(
            items=[_transaction_dto(t, labels) for t, labels in items],
            next_cursor=next_cursor,
        )


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------
class CreateBudget:
    def __init__(
        self,
        budgets: BudgetRepository,
        categories: CategoryRepository,
        profiles: ProfileRepository,
    ) -> None:
        self._budgets = budgets
        self._categories = categories
        self._profiles = profiles

    def execute(self, user_id: UUID, data: CreateBudgetInput) -> BudgetDTO:
        category = self._categories.get_by_id(data.category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(data.category_id)
        if category.type is not TransactionType.EXPENSE:
            msg = "A budget can only target an expense category."
            raise ValidationError(msg)
        # Budgets are denominated in the user's base currency.
        profile = self._profiles.get_by_user(user_id)
        currency = profile.base_currency.value if profile else DEFAULT_CURRENCY
        budget = Budget(
            user_id=user_id,
            category_id=data.category_id,
            amount=Money.from_minor_units(data.amount_minor, currency),
            period=data.period,
            start_date=data.start_date,
            is_active=data.is_active,
        )
        return _budget_dto(self._budgets.add(budget))


class UpdateBudget:
    def __init__(self, budgets: BudgetRepository, categories: CategoryRepository) -> None:
        self._budgets = budgets
        self._categories = categories

    def execute(self, user_id: UUID, budget_id: UUID, data: UpdateBudgetInput) -> BudgetDTO:
        budget = self._budgets.get_by_id(budget_id, user_id)
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        currency = budget.amount.currency
        updated = apply_patch(
            budget,
            data,
            fields={"amount_minor": ("amount", lambda m: Money.from_minor_units(m, currency))},
            nullable={"start_date"},
        )
        category = self._categories.get_by_id(updated.category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(updated.category_id)
        if category.type is not TransactionType.EXPENSE:
            msg = "A budget can only target an expense category."
            raise ValidationError(msg)
        return _budget_dto(self._budgets.update(updated))


class ListBudgets:
    def __init__(self, budgets: BudgetRepository) -> None:
        self._budgets = budgets

    def execute(self, user_id: UUID) -> list[BudgetDTO]:
        return [_budget_dto(b) for b in self._budgets.list_for_user(user_id)]


class GetBudgetDetail:
    def __init__(self, budgets: BudgetRepository) -> None:
        self._budgets = budgets

    def execute(self, user_id: UUID, budget_id: UUID) -> BudgetDTO:
        budget = self._budgets.get_by_id(budget_id, user_id)
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        return _budget_dto(budget)


class DeleteBudget:
    def __init__(self, budgets: BudgetRepository) -> None:
        self._budgets = budgets

    def execute(self, user_id: UUID, budget_id: UUID) -> None:
        if not self._budgets.delete(budget_id, user_id):
            raise BudgetNotFoundError(budget_id)
