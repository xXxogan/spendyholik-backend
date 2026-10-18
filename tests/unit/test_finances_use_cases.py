from datetime import date
from uuid import uuid4

import pytest

from accounts.domain.entities import Profile
from finances.application.dto import (
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
    ListTransactionsInput,
    UpdateCategoryInput,
)
from finances.application.use_cases import (
    ArchiveAccount,
    CreateAccount,
    CreateBudget,
    CreateCategory,
    CreateTransaction,
    DeleteCategory,
    ListAccounts,
    ListTransactions,
    UpdateCategory,
)
from finances.domain.enums import AccountType, TransactionType
from finances.domain.exceptions import (
    AccountArchivedError,
    AccountNotFoundError,
    CategoryCycleError,
    CategoryInUseError,
)
from shared.domain.currency_code import CurrencyCode
from shared.exceptions import ValidationError
from tests.fakes import (
    InMemoryAccountRepository,
    InMemoryBudgetRepository,
    InMemoryCategoryRepository,
    InMemoryProfileRepository,
    InMemoryTransactionRepository,
)

USER = uuid4()


def _account(repo, name="Карта", type=AccountType.DEBIT, currency="RUB", **kw):
    return CreateAccount(repo).execute(
        USER, CreateAccountInput(name=name, type=type, currency=currency, **kw)
    )


class TestAccounts:
    def test_create_and_list(self):
        repo = InMemoryAccountRepository()
        dto = _account(repo)
        assert dto.initial_balance.to_minor_units() == 0
        assert len(ListAccounts(repo).execute(USER)) == 1

    def test_archived_account_excluded_from_list(self):
        repo = InMemoryAccountRepository()
        dto = _account(repo)
        ArchiveAccount(repo).execute(USER, dto.id)
        assert ListAccounts(repo).execute(USER) == []
        assert len(ListAccounts(repo).execute(USER, include_archived=True)) == 1


class TestCreateTransaction:
    def test_expense_amount_uses_account_currency_and_minor_units(self):
        accounts = InMemoryAccountRepository()
        categories = InMemoryCategoryRepository()
        transactions = InMemoryTransactionRepository()
        acct = _account(accounts)
        cat = CreateCategory(categories).execute(
            USER, CreateCategoryInput(name="Еда", type=TransactionType.EXPENSE)
        )
        dto = CreateTransaction(accounts, categories, transactions).execute(
            USER,
            CreateTransactionInput(
                account_id=acct.id,
                type=TransactionType.EXPENSE,
                amount_minor=1240_00,
                date=date(2026, 3, 15),
                category_id=cat.id,
            ),
        )
        assert dto.amount.to_minor_units() == 1240_00
        assert dto.amount.currency == "RUB"

    def test_archived_account_rejected(self):
        accounts = InMemoryAccountRepository()
        acct = _account(accounts)
        ArchiveAccount(accounts).execute(USER, acct.id)
        with pytest.raises(AccountArchivedError):
            CreateTransaction(
                accounts, InMemoryCategoryRepository(), InMemoryTransactionRepository()
            ).execute(
                USER,
                CreateTransactionInput(
                    account_id=acct.id,
                    type=TransactionType.EXPENSE,
                    amount_minor=100,
                    date=date(2026, 3, 15),
                ),
            )

    def test_transfer_requires_destination_account(self):
        accounts = InMemoryAccountRepository()
        acct = _account(accounts)
        with pytest.raises(AccountNotFoundError):
            CreateTransaction(
                accounts, InMemoryCategoryRepository(), InMemoryTransactionRepository()
            ).execute(
                USER,
                CreateTransactionInput(
                    account_id=acct.id,
                    type=TransactionType.TRANSFER,
                    amount_minor=100,
                    date=date(2026, 3, 15),
                    transfer_to_account_id=uuid4(),
                ),
            )

    def test_cross_currency_transfer_rejected(self):
        accounts = InMemoryAccountRepository()
        src = _account(accounts, currency="RUB")
        dst = _account(accounts, name="USD", currency="USD")
        with pytest.raises(ValidationError):
            CreateTransaction(
                accounts, InMemoryCategoryRepository(), InMemoryTransactionRepository()
            ).execute(
                USER,
                CreateTransactionInput(
                    account_id=src.id,
                    type=TransactionType.TRANSFER,
                    amount_minor=100,
                    date=date(2026, 3, 15),
                    transfer_to_account_id=dst.id,
                ),
            )

    def test_category_type_mismatch_rejected(self):
        accounts = InMemoryAccountRepository()
        categories = InMemoryCategoryRepository()
        acct = _account(accounts)
        income_cat = CreateCategory(categories).execute(
            USER, CreateCategoryInput(name="Зарплата", type=TransactionType.INCOME)
        )
        with pytest.raises(ValidationError):
            CreateTransaction(accounts, categories, InMemoryTransactionRepository()).execute(
                USER,
                CreateTransactionInput(
                    account_id=acct.id,
                    type=TransactionType.EXPENSE,
                    amount_minor=100,
                    date=date(2026, 3, 15),
                    category_id=income_cat.id,
                ),
            )


class TestListTransactions:
    def test_cursor_pagination(self):
        accounts = InMemoryAccountRepository()
        transactions = InMemoryTransactionRepository()
        acct = _account(accounts)
        for i in range(5):
            CreateTransaction(accounts, InMemoryCategoryRepository(), transactions).execute(
                USER,
                CreateTransactionInput(
                    account_id=acct.id,
                    type=TransactionType.EXPENSE,
                    amount_minor=100 + i,
                    date=date(2026, 3, i + 1),
                ),
            )
        first = ListTransactions(transactions).execute(USER, ListTransactionsInput(limit=2))
        assert len(first.items) == 2
        assert first.next_cursor is not None
        second = ListTransactions(transactions).execute(
            USER, ListTransactionsInput(limit=2, cursor=first.next_cursor)
        )
        assert len(second.items) == 2
        ids = {t.id for t in first.items} | {t.id for t in second.items}
        assert len(ids) == 4  # no overlap


class TestCategories:
    def test_cycle_detection_on_update(self):
        repo = InMemoryCategoryRepository()
        parent = CreateCategory(repo).execute(
            USER, CreateCategoryInput(name="Родитель", type=TransactionType.EXPENSE)
        )
        child = CreateCategory(repo).execute(
            USER,
            CreateCategoryInput(name="Ребёнок", type=TransactionType.EXPENSE, parent_id=parent.id),
        )
        with pytest.raises(CategoryCycleError):
            UpdateCategory(repo).execute(USER, parent.id, UpdateCategoryInput(parent_id=child.id))

    def test_delete_in_use_category_rejected(self):
        categories = InMemoryCategoryRepository()
        transactions = InMemoryTransactionRepository()
        accounts = InMemoryAccountRepository()
        acct = _account(accounts)
        cat = CreateCategory(categories).execute(
            USER, CreateCategoryInput(name="Еда", type=TransactionType.EXPENSE)
        )
        CreateTransaction(accounts, categories, transactions).execute(
            USER,
            CreateTransactionInput(
                account_id=acct.id,
                type=TransactionType.EXPENSE,
                amount_minor=100,
                date=date(2026, 3, 15),
                category_id=cat.id,
            ),
        )
        # Wire category-usage check to the transaction repo.
        categories.has_transactions = lambda cid, uid: transactions.category_is_used(cid)
        with pytest.raises(CategoryInUseError):
            DeleteCategory(categories).execute(USER, cat.id)


class TestBudgets:
    def test_budget_requires_expense_category(self):
        budgets = InMemoryBudgetRepository()
        categories = InMemoryCategoryRepository()
        income = CreateCategory(categories).execute(
            USER, CreateCategoryInput(name="Зарплата", type=TransactionType.INCOME)
        )
        with pytest.raises(ValidationError):
            CreateBudget(budgets, categories, InMemoryProfileRepository()).execute(
                USER, CreateBudgetInput(category_id=income.id, amount_minor=1000_00)
            )

    def test_budget_uses_profile_base_currency(self):
        budgets = InMemoryBudgetRepository()
        categories = InMemoryCategoryRepository()
        profiles = InMemoryProfileRepository()
        profiles.add(Profile(user_id=USER, base_currency=CurrencyCode("USD")))
        food = CreateCategory(categories).execute(
            USER, CreateCategoryInput(name="Еда", type=TransactionType.EXPENSE)
        )
        budget = CreateBudget(budgets, categories, profiles).execute(
            USER, CreateBudgetInput(category_id=food.id, amount_minor=1000_00)
        )
        assert budget.amount.currency == "USD"
