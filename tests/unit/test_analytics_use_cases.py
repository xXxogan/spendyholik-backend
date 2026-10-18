from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounts.domain.entities import Profile
from analytics.application.use_cases import (
    GetDashboard,
    GetMonthlyTrend,
    GetSpendingByCategory,
    GetSummary,
)
from finances.application.dto import (
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
)
from finances.application.use_cases import (
    ArchiveAccount,
    CreateAccount,
    CreateBudget,
    CreateCategory,
    CreateTransaction,
)
from finances.domain.entities import ExchangeRate
from shared.domain.currency_code import CurrencyCode
from tests.fakes import (
    FakeClock,
    InMemoryAccountRepository,
    InMemoryBudgetRepository,
    InMemoryCategoryRepository,
    InMemoryExchangeRateRepository,
    InMemoryProfileRepository,
    InMemoryTransactionRepository,
)

USER = uuid4()
TODAY = date(2026, 3, 15)  # a Sunday


class World:
    def __init__(self) -> None:
        self.accounts = InMemoryAccountRepository()
        self.categories = InMemoryCategoryRepository()
        self.transactions = InMemoryTransactionRepository(self.accounts)
        self.budgets = InMemoryBudgetRepository()
        self.profiles = InMemoryProfileRepository()
        self.rates = InMemoryExchangeRateRepository()
        self.profiles.add(Profile(user_id=USER))
        self.acct = self.account("RUB", 100000_00)
        self.food = CreateCategory(self.categories).execute(
            USER, CreateCategoryInput(name="Еда", type="expense")
        )
        self.salary = CreateCategory(self.categories).execute(
            USER, CreateCategoryInput(name="Зарплата", type="income")
        )
        self.tx(self.acct.id, "income", 50000_00, self.salary.id)
        self.tx(self.acct.id, "expense", 20000_00, self.food.id)

    def account(self, currency, initial=0):
        return CreateAccount(self.accounts).execute(
            USER,
            CreateAccountInput(
                name=f"Счёт {currency}",
                type="debit",
                currency=currency,
                initial_balance_minor=initial,
            ),
        )

    def tx(self, account_id, type_, amount, category_id, on=TODAY):
        CreateTransaction(self.accounts, self.categories, self.transactions).execute(
            USER,
            CreateTransactionInput(
                account_id=account_id,
                type=type_,
                amount_minor=amount,
                date=on,
                category_id=category_id,
            ),
        )

    def rate(self, base, target, rate):
        self.rates.add(ExchangeRate(CurrencyCode(base), CurrencyCode(target), Decimal(rate), TODAY))

    def dashboard(self):
        return GetDashboard(
            self.accounts,
            self.transactions,
            self.budgets,
            self.profiles,
            self.rates,
            FakeClock(TODAY),
        ).execute(USER)


class TestGetDashboard:
    def test_computes_totals_and_net(self):
        dash = World().dashboard()
        # initial 100000 + income 50000 - expense 20000 = 130000
        assert dash.total_balance.to_minor_units() == 130000_00
        assert dash.income_this_month.to_minor_units() == 50000_00
        assert dash.expense_this_month.to_minor_units() == 20000_00
        assert dash.net_this_month.to_minor_units() == 30000_00
        assert dash.excluded_currencies == []

    def test_converts_foreign_accounts_into_base_currency(self):
        w = World()
        usd = w.account("USD", 100_00)
        w.tx(usd.id, "expense", 10_00, w.food.id)
        w.rate("USD", "RUB", "90")
        dash = w.dashboard()
        # 130000 RUB + (100 - 10) USD * 90
        assert dash.total_balance.currency == "RUB"
        assert dash.total_balance.to_minor_units() == 130000_00 + 8100_00
        assert dash.expense_this_month.to_minor_units() == 20000_00 + 900_00

    def test_uses_inverse_rate(self):
        w = World()
        w.account("USD", 100_00)
        w.rate("RUB", "USD", "0.01")
        assert w.dashboard().total_balance.to_minor_units() == 130000_00 + 10000_00

    def test_currency_without_rate_is_excluded_not_fatal(self):
        w = World()
        w.account("USD", 100_00)
        dash = w.dashboard()
        assert dash.total_balance.to_minor_units() == 130000_00
        assert dash.excluded_currencies == ["USD"]

    def test_archived_accounts_are_excluded(self):
        w = World()
        old = w.account("RUB", 5000_00)
        w.tx(old.id, "expense", 1000_00, w.food.id)
        ArchiveAccount(w.accounts).execute(USER, old.id)
        dash = w.dashboard()
        assert dash.total_balance.to_minor_units() == 130000_00
        assert dash.expense_this_month.to_minor_units() == 20000_00

    def test_budget_windows_follow_period(self):
        w = World()
        # An expense earlier this month, but before this week's Monday (9th).
        w.tx(w.acct.id, "expense", 1000_00, w.food.id, on=date(2026, 3, 2))
        create = CreateBudget(w.budgets, w.categories, w.profiles)
        create.execute(USER, CreateBudgetInput(category_id=w.food.id, amount_minor=50000_00))
        create.execute(
            USER,
            CreateBudgetInput(category_id=w.food.id, amount_minor=25000_00, period="weekly"),
        )
        statuses = {b.limit.to_minor_units(): b for b in w.dashboard().budgets}
        assert statuses[50000_00].spent.to_minor_units() == 21000_00  # whole month
        assert statuses[25000_00].spent.to_minor_units() == 20000_00  # since Monday 9th
        assert statuses[25000_00].ratio == 0.8


class TestSummary:
    def test_income_expense_net(self):
        w = World()
        summary = GetSummary(w.transactions, w.profiles, w.rates).execute(USER)
        assert summary.net.to_minor_units() == 30000_00


class TestSpendingByCategory:
    def test_groups_expenses(self):
        w = World()
        result = GetSpendingByCategory(w.transactions, w.categories, w.profiles, w.rates).execute(
            USER
        )
        assert len(result) == 1
        assert result[0].category_name == "Еда"
        assert result[0].amount.to_minor_units() == 20000_00
        assert result[0].ratio == 1.0


class TestMonthlyTrend:
    def test_returns_ordered_points(self):
        w = World()
        points = GetMonthlyTrend(w.transactions, w.profiles, w.rates, FakeClock(TODAY)).execute(
            USER, months=1
        )
        assert len(points) == 1
        assert points[0].income.to_minor_units() == 50000_00
        assert points[0].expense.to_minor_units() == 20000_00

    def test_months_are_clamped(self):
        w = World()
        trend = GetMonthlyTrend(w.transactions, w.profiles, w.rates, FakeClock(TODAY))
        assert len(trend.execute(USER, months=100_000)) == 36
        assert len(trend.execute(USER, months=0)) == 1
