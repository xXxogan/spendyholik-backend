"""Use cases for the finances bounded context (accounts, categories,
transactions, budgets)."""

from __future__ import annotations

from uuid import UUID

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


def _transaction_dto(t: Transaction) -> TransactionDTO:
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
        credit_limit = account.credit_limit
        if data.credit_limit_minor is not None:
            credit_limit = Money.from_minor_units(data.credit_limit_minor, account.currency.value)
        updated = Account(
            id=account.id,
            user_id=user_id,
            name=data.name if data.name is not None else account.name,
            type=data.type if data.type is not None else account.type,
            currency=account.currency,
            initial_balance=account.initial_balance,
            color=CategoryColor(data.color) if data.color is not None else account.color,
            last4=account.last4 if data.last4 is None else data.last4,
            credit_limit=credit_limit,
            interest_rate=data.interest_rate if data.interest_rate is not None else account.interest_rate,
            is_archived=account.is_archived,
        )
        return _account_dto(self._accounts.update(updated))


class ArchiveAccount:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, account_id: UUID) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        archived = Account(
            id=account.id,
            user_id=user_id,
            name=account.name,
            type=account.type,
            currency=account.currency,
            initial_balance=account.initial_balance,
            color=account.color,
            last4=account.last4,
            credit_limit=account.credit_limit,
            interest_rate=account.interest_rate,
            is_archived=True,
        )
        return _account_dto(self._accounts.update(archived))


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
        parent_id = category.parent_id if data.parent_id is None else data.parent_id
        if parent_id is not None:
            if parent_id == category_id:
                raise CategoryCycleError
            parent = self._categories.get_by_id(parent_id, user_id)
            if parent is None:
                raise CategoryNotFoundError(parent_id)
            if self._categories.is_ancestor(user_id, category_id, parent_id):
                raise CategoryCycleError
        updated = Category(
            id=category.id,
            user_id=user_id,
            name=data.name if data.name is not None else category.name,
            type=category.type,
            icon=data.icon if data.icon is not None else category.icon,
            color=CategoryColor(data.color) if data.color is not None else category.color,
            parent_id=parent_id,
            is_system=category.is_system,
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

    def _require_account(self, user_id: UUID, account_id: UUID, *, allow_archived: bool = False) -> Account:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        if account.is_archived and not allow_archived:
            raise AccountArchivedError
        return account

    def _require_category(self, user_id: UUID, category_id: UUID | None, tx_type: TransactionType) -> None:
        if category_id is None:
            return
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if tx_type in (TransactionType.EXPENSE, TransactionType.INCOME) and category.type != tx_type:
            msg = f"Category type {category.type.value} does not match transaction type {tx_type.value}."
            raise ValidationError(msg)

    def validate(self, user_id: UUID, data: CreateTransactionInput) -> None:
        account = self._require_account(user_id, data.account_id)
        if data.type is TransactionType.TRANSFER:
            dest = self._require_account(user_id, data.transfer_to_account_id or data.account_id)
            if dest.currency != account.currency:
                msg = "Cross-currency transfers are not supported yet."
                raise ValidationError(msg)
        self._require_category(user_id, data.category_id, data.type)


class CreateTransaction:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._guard = _TransactionGuard(accounts, categories, transactions)
        self._accounts = accounts
        self._transactions = transactions

    def execute(self, user_id: UUID, data: CreateTransactionInput) -> TransactionDTO:
        self._guard.validate(user_id, data)
        account = self._accounts.get_by_id(data.account_id, user_id)
        assert account is not None  # validated above
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
        tx = self._transactions.get_by_id(transaction_id, user_id)
        if tx is None:
            raise TransactionNotFoundError(transaction_id)
        return _transaction_dto(tx)


class UpdateTransaction:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._guard = _TransactionGuard(accounts, categories, transactions)
        self._accounts = accounts
        self._transactions = transactions

    def execute(self, user_id: UUID, transaction_id: UUID, data: UpdateTransactionInput) -> TransactionDTO:
        tx = self._transactions.get_by_id(transaction_id, user_id)
        if tx is None:
            raise TransactionNotFoundError(transaction_id)
        account_id = data.account_id if data.account_id is not None else tx.account_id
        tx_type = tx.type
        transfer_to = tx.transfer_to_account_id if data.transfer_to_account_id is None else data.transfer_to_account_id
        category_id = tx.category_id if data.category_id is None else data.category_id
        self._guard._require_account(user_id, account_id)
        if tx_type is TransactionType.TRANSFER:
            dest = self._guard._require_account(user_id, transfer_to or account_id)
            src = self._guard._require_account(user_id, account_id)
            if dest.currency != src.currency:
                msg = "Cross-currency transfers are not supported yet."
                raise ValidationError(msg)
        self._guard._require_category(user_id, category_id, tx_type)
        account = self._accounts.get_by_id(account_id, user_id)
        assert account is not None
        updated = Transaction(
            id=tx.id,
            user_id=user_id,
            account_id=account_id,
            category_id=category_id,
            type=tx_type,
            amount=(
                tx.amount
                if data.amount_minor is None
                else Money.from_minor_units(data.amount_minor, account.currency.value)
            ),
            date=data.date if data.date is not None else tx.date,
            time=tx.time if data.time is None else data.time,
            note=tx.note if data.note is None else data.note,
            receipt_id=tx.receipt_id,
            transfer_to_account_id=transfer_to,
        )
        return _transaction_dto(self._transactions.update(updated))


class DeleteTransaction:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, transaction_id: UUID) -> None:
        tx = self._transactions.get_by_id(transaction_id, user_id)
        if tx is None:
            raise TransactionNotFoundError(transaction_id)
        self._transactions.delete(transaction_id, user_id)


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
            items=[_transaction_dto(t) for t in items],
            next_cursor=next_cursor,
        )


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------
class CreateBudget:
    def __init__(self, budgets: BudgetRepository, categories: CategoryRepository) -> None:
        self._budgets = budgets
        self._categories = categories

    def execute(self, user_id: UUID, data: CreateBudgetInput) -> BudgetDTO:
        category = self._categories.get_by_id(data.category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(data.category_id)
        if category.type is not TransactionType.EXPENSE:
            msg = "A budget can only target an expense category."
            raise ValidationError(msg)
        # Budgets are denominated in the user's base currency (RUB by default).
        budget = Budget(
            user_id=user_id,
            category_id=data.category_id,
            amount=Money.from_minor_units(data.amount_minor, DEFAULT_CURRENCY),
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
        category_id = budget.category_id if data.category_id is None else data.category_id
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if category.type is not TransactionType.EXPENSE:
            msg = "A budget can only target an expense category."
            raise ValidationError(msg)
        updated = Budget(
            id=budget.id,
            user_id=user_id,
            category_id=category_id,
            amount=(
                budget.amount
                if data.amount_minor is None
                else Money.from_minor_units(data.amount_minor, budget.amount.currency)
            ),
            period=budget.period if data.period is None else data.period,
            start_date=budget.start_date if data.start_date is None else data.start_date,
            is_active=budget.is_active if data.is_active is None else data.is_active,
        )
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
        if self._budgets.get_by_id(budget_id, user_id) is None:
            raise BudgetNotFoundError(budget_id)
        self._budgets.delete(budget_id, user_id)
