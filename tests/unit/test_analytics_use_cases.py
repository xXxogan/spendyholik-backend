from datetime import date
from uuid import uuid4

from analytics.application.use_cases import GetDashboard, GetMonthlyTrend, GetSpendingByCategory
from finances.application.dto import CreateAccountInput, CreateCategoryInput, CreateTransactionInput
from finances.application.use_cases import CreateAccount, CreateCategory, CreateTransaction
from tests.fakes import (
    FakeClock,
    InMemoryAccountRepository,
    InMemoryBudgetRepository,
    InMemoryCategoryRepository,
    InMemoryTransactionRepository,
)

USER = uuid4()
TODAY = date(2026, 3, 15)


def _setup():
    accounts = InMemoryAccountRepository()
    categories = InMemoryCategoryRepository()
    transactions = InMemoryTransactionRepository()
    acct = CreateAccount(accounts).execute(USER, CreateAccountInput(name="Счёт", type="debit", currency="RUB",
                                                                    initial_balance_minor=100000_00))
    food = CreateCategory(categories).execute(USER, CreateCategoryInput(name="Еда", type="expense"))
    salary = CreateCategory(categories).execute(USER, CreateCategoryInput(name="Зарплата", type="income"))
    CreateTransaction(accounts, categories, transactions).execute(
        USER, CreateTransactionInput(account_id=acct.id, type="income", amount_minor=50000_00,
                                     date=TODAY, category_id=salary.id)
    )
    CreateTransaction(accounts, categories, transactions).execute(
        USER, CreateTransactionInput(account_id=acct.id, type="expense", amount_minor=20000_00,
                                     date=TODAY, category_id=food.id)
    )
    return accounts, categories, transactions, acct


class TestGetDashboard:
    def test_computes_totals_and_net(self):
        accounts, categories, transactions, acct = _setup()
        budgets = InMemoryBudgetRepository()
        dash = GetDashboard(accounts, transactions, budgets, FakeClock(TODAY)).execute(USER)
        # initial 100000 + income 50000 - expense 20000 = 130000
        assert dash.total_balance.to_minor_units() == 130000_00
        assert dash.income_this_month.to_minor_units() == 50000_00
        assert dash.expense_this_month.to_minor_units() == 20000_00
        assert dash.net_this_month.to_minor_units() == 30000_00


class TestSpendingByCategory:
    def test_groups_expenses(self):
        accounts, categories, transactions, acct = _setup()
        result = GetSpendingByCategory(transactions, categories).execute(USER)
        assert len(result) == 1
        assert result[0].category_name == "Еда"
        assert result[0].amount.to_minor_units() == 20000_00


class TestMonthlyTrend:
    def test_returns_ordered_points(self):
        accounts, categories, transactions, acct = _setup()
        points = GetMonthlyTrend(transactions, FakeClock(TODAY)).execute(USER, months=1)
        assert len(points) == 1
        assert points[0].income.to_minor_units() == 50000_00
        assert points[0].expense.to_minor_units() == 20000_00
