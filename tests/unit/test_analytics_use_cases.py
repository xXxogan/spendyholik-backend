from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounts.domain.entities import Profile
from analytics.application.use_cases import (
    GetDashboard,
    GetMonthlyTrend,
    GetSpendingByCategory,
    GetSummary,
    GetTrend,
)
from finances.application.dto import (
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
)
from finances.application.use_cases import (
    ArchiveAccount,
    BudgetReporter,
    CreateAccount,
    CreateBudget,
    CreateCategory,
    CreateTransaction,
)
from finances.domain.entities import ExchangeRate
from finances.domain.enums import Granularity
from shared.domain.currency_code import CurrencyCode
from shared.exceptions import ValidationError
from tests.fakes import (
    FakeClock,
    InMemoryAccountRepository,
    InMemoryBalanceReader,
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
            InMemoryBalanceReader(self.transactions),
            self.categories,
        ).execute(USER)

    def category(self, name, parent_id=None):
        return CreateCategory(self.categories).execute(
            USER, CreateCategoryInput(name=name, type="expense", parent_id=parent_id)
        )

    def create_budget(self):
        return CreateBudget(
            self.budgets,
            self.categories,
            self.profiles,
            BudgetReporter(self.transactions, self.categories, self.rates, FakeClock(TODAY)),
        )


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
        ArchiveAccount(w.accounts, InMemoryBalanceReader()).execute(USER, old.id)
        dash = w.dashboard()
        assert dash.total_balance.to_minor_units() == 130000_00
        assert dash.expense_this_month.to_minor_units() == 20000_00

    def test_budget_windows_follow_period(self):
        w = World()
        home = w.category("Дом")
        # Expenses earlier this month, but before this week's Monday (9th).
        w.tx(w.acct.id, "expense", 1000_00, w.food.id, on=date(2026, 3, 2))
        w.tx(w.acct.id, "expense", 3000_00, home.id, on=date(2026, 3, 2))
        w.tx(w.acct.id, "expense", 2000_00, home.id)
        create = w.create_budget()
        create.execute(USER, CreateBudgetInput(category_id=w.food.id, amount_minor=50000_00))
        create.execute(
            USER, CreateBudgetInput(category_id=home.id, amount_minor=2500_00, period="weekly")
        )
        statuses = {b.limit.to_minor_units(): b for b in w.dashboard().budgets}
        assert statuses[50000_00].spent.to_minor_units() == 21000_00  # whole month
        assert statuses[2500_00].spent.to_minor_units() == 2000_00  # since Monday 9th
        assert statuses[2500_00].ratio == 0.8

    def test_budget_counts_subcategories(self):
        w = World()
        cafe = w.category("Кафе", parent_id=w.food.id)
        w.tx(w.acct.id, "expense", 500_00, cafe.id)
        w.create_budget().execute(
            USER, CreateBudgetInput(category_id=w.food.id, amount_minor=50000_00)
        )
        [status] = w.dashboard().budgets
        assert status.spent.to_minor_units() == 20500_00


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

    def test_subcategories_roll_up_into_their_root(self):
        w = World()
        cafe = w.category("Кафе", parent_id=w.food.id)
        coffee = w.category("Кофе", parent_id=cafe.id)
        home = w.category("Дом")
        w.tx(w.acct.id, "expense", 1000_00, coffee.id)
        w.tx(w.acct.id, "expense", 9000_00, home.id)
        result = GetSpendingByCategory(w.transactions, w.categories, w.profiles, w.rates).execute(
            USER
        )
        assert [(r.category.name, r.amount.to_minor_units()) for r in result] == [
            ("Еда", 21000_00),
            ("Дом", 9000_00),
        ]
        assert result[0].category.id == w.food.id


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


class TestTrend:
    def _trend(self, w):
        return GetTrend(w.transactions, w.profiles, w.rates, FakeClock(TODAY))

    def test_days_default_to_the_last_week(self):
        w = World()
        w.tx(w.acct.id, "expense", 100_00, w.food.id, on=date(2026, 3, 10))
        points = self._trend(w).execute(USER, Granularity.DAY)
        assert [p.start for p in points][0] == date(2026, 3, 9)
        assert len(points) == 7
        by_day = {p.start: p.expense.to_minor_units() for p in points}
        assert by_day[date(2026, 3, 10)] == 100_00
        assert by_day[TODAY] == 20000_00

    def test_months_default_to_half_a_year(self):
        points = self._trend(World()).execute(USER, Granularity.MONTH)
        assert [p.start for p in points] == [
            date(2025, 10, 1),
            date(2025, 11, 1),
            date(2025, 12, 1),
            date(2026, 1, 1),
            date(2026, 2, 1),
            date(2026, 3, 1),
        ]

    def test_years_default_to_three(self):
        w = World()
        w.tx(w.acct.id, "income", 1_00, w.salary.id, on=date(2024, 6, 1))
        points = self._trend(w).execute(USER, Granularity.YEAR)
        assert [p.start for p in points] == [date(2024, 1, 1), date(2025, 1, 1), date(2026, 1, 1)]
        assert points[0].income.to_minor_units() == 1_00
        assert points[2].income.to_minor_units() == 50000_00

    def test_explicit_range(self):
        points = self._trend(World()).execute(
            USER, Granularity.DAY, date(2026, 3, 1), date(2026, 3, 3)
        )
        assert [p.start for p in points] == [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]

    def test_too_many_points_rejected(self):
        with pytest.raises(ValidationError):
            self._trend(World()).execute(USER, Granularity.DAY, date(2020, 1, 1), TODAY)

    def test_reversed_range_rejected(self):
        with pytest.raises(ValidationError):
            self._trend(World()).execute(USER, Granularity.DAY, TODAY, date(2026, 3, 1))
