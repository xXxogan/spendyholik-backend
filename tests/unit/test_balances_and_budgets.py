"""Account balances (R-20/21/23), budgets with spending (R-50/51) and subcategories (R-31)."""

from datetime import date
from uuid import uuid4

import pytest

from finances.application.dto import (
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
    ListTransactionsInput,
    UpdateAccountInput,
    UpdateBudgetInput,
)
from finances.application.use_cases import (
    ArchiveAccount,
    BudgetReporter,
    CreateAccount,
    CreateBudget,
    CreateCategory,
    CreateTransaction,
    GetAccountDetail,
    GetBalanceHistory,
    ListBudgets,
    ListCategories,
    ListTransactions,
    UnarchiveAccount,
    UpdateAccount,
    UpdateBudget,
)
from finances.domain.exceptions import BudgetAlreadyExistsError
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
TODAY = date(2026, 3, 18)  # a Wednesday


class World:
    def __init__(self) -> None:
        self.accounts = InMemoryAccountRepository()
        self.categories = InMemoryCategoryRepository()
        self.transactions = InMemoryTransactionRepository(self.accounts, self.categories)
        self.budgets = InMemoryBudgetRepository()
        self.balances = InMemoryBalanceReader(self.transactions)
        self.reporter = BudgetReporter(
            self.transactions, self.categories, InMemoryExchangeRateRepository(), FakeClock(TODAY)
        )

    def account(self, initial_minor=1000_00, name="Карта"):
        return CreateAccount(self.accounts).execute(
            USER,
            CreateAccountInput(
                name=name, type="debit", currency="RUB", initial_balance_minor=initial_minor
            ),
        )

    def category(self, name="Еда", parent_id=None, type_="expense"):
        return CreateCategory(self.categories).execute(
            USER, CreateCategoryInput(name=name, type=type_, parent_id=parent_id)
        )

    def tx(self, account_id, amount_minor, day=TODAY, type_="expense", **kw):
        return CreateTransaction(self.accounts, self.categories, self.transactions).execute(
            USER,
            CreateTransactionInput(
                account_id=account_id, type=type_, amount_minor=amount_minor, date=day, **kw
            ),
        )

    def balance(self, account_id) -> int:
        dto = GetAccountDetail(self.accounts, self.balances).execute(USER, account_id)
        return dto.balance.to_minor_units()

    def budget(self, category_id, **fields):
        data = {"category_id": category_id, "amount_minor": 500_00} | fields
        return CreateBudget(
            self.budgets, self.categories, InMemoryProfileRepository(), self.reporter
        ).execute(USER, CreateBudgetInput.model_validate(data))


class TestBalance:
    def test_balance_follows_income_expense_and_transfers(self):
        w = World()
        card = w.account(1000_00)
        cash = w.account(0, name="Наличные")
        w.tx(card.id, 300_00)
        w.tx(card.id, 50_00, type_="income")
        w.tx(card.id, 200_00, type_="transfer", transfer_to_account_id=cash.id)
        assert w.balance(card.id) == 1000_00 - 300_00 + 50_00 - 200_00
        assert w.balance(cash.id) == 200_00

    def test_setting_the_balance_shifts_the_initial_one(self):
        w = World()
        card = w.account(1000_00)
        w.tx(card.id, 300_00)
        updated = UpdateAccount(w.accounts, w.balances).execute(
            USER, card.id, UpdateAccountInput(balance_minor=2000_00)
        )
        assert updated.balance.to_minor_units() == 2000_00
        assert updated.initial_balance.to_minor_units() == 2300_00
        assert w.balance(card.id) == 2000_00

    def test_unarchive(self):
        w = World()
        card = w.account()
        ArchiveAccount(w.accounts, w.balances).execute(USER, card.id)
        dto = UnarchiveAccount(w.accounts, w.balances).execute(USER, card.id)
        assert dto.is_archived is False


class TestBalanceHistory:
    def test_points_before_window_per_day_and_today(self):
        w = World()
        card = w.account(1000_00)
        w.tx(card.id, 100_00, day=date(2026, 1, 1))  # before the window
        w.tx(card.id, 50_00, day=date(2026, 3, 2))
        w.tx(card.id, 25_00, day=date(2026, 3, 2))
        w.tx(card.id, 10_00, day=date(2026, 3, 10), type_="income")
        points = GetBalanceHistory(w.accounts, w.balances, FakeClock(TODAY)).execute(
            USER, card.id, weeks=6
        )
        assert [(p.at, p.balance.to_minor_units()) for p in points] == [
            (date(2026, 2, 4), 900_00),
            (date(2026, 3, 2), 825_00),
            (date(2026, 3, 10), 835_00),
            (TODAY, 835_00),
        ]

    def test_weeks_out_of_range_rejected(self):
        w = World()
        card = w.account()
        with pytest.raises(ValidationError):
            GetBalanceHistory(w.accounts, w.balances, FakeClock(TODAY)).execute(
                USER, card.id, weeks=0
            )


class TestSubcategories:
    def test_category_filter_includes_subcategories(self):
        w = World()
        card = w.account()
        food = w.category("Еда")
        cafe = w.category("Кафе", parent_id=food.id)
        other = w.category("Транспорт")
        w.tx(card.id, 10_00, category_id=food.id)
        w.tx(card.id, 20_00, category_id=cafe.id)
        w.tx(card.id, 30_00, category_id=other.id)
        page = ListTransactions(w.transactions).execute(
            USER, ListTransactionsInput(category_id=food.id)
        )
        assert sorted(t.amount.to_minor_units() for t in page.items) == [10_00, 20_00]

    def test_categories_carry_transaction_counts(self):
        w = World()
        food = w.category("Еда")
        w.categories.counts = {food.id: 3}
        [dto] = ListCategories(w.categories).execute(USER)
        assert dto.transaction_count == 3


class TestBudgets:
    def test_monthly_budget_reports_period_and_spending_with_subcategories(self):
        w = World()
        card = w.account()
        food = w.category("Еда")
        cafe = w.category("Кафе", parent_id=food.id)
        w.tx(card.id, 100_00, category_id=food.id, day=date(2026, 3, 1))
        w.tx(card.id, 40_00, category_id=cafe.id, day=date(2026, 3, 31))
        w.tx(card.id, 999_00, category_id=food.id, day=date(2026, 2, 28))  # previous month
        dto = w.budget(food.id)
        assert (dto.period_start, dto.period_end) == (date(2026, 3, 1), date(2026, 3, 31))
        assert dto.spent.to_minor_units() == 140_00
        assert dto.category.name == "Еда"

    def test_weekly_budget_runs_monday_to_sunday(self):
        w = World()
        dto = w.budget(w.category().id, period="weekly")
        assert (dto.period_start, dto.period_end) == (date(2026, 3, 16), date(2026, 3, 22))

    def test_one_time_budget_needs_both_dates(self):
        w = World()
        with pytest.raises(ValidationError) as exc:
            w.budget(w.category().id, period="one_time", start_date="2026-03-01")
        assert exc.value.errors == {"end_date": "required"}

    def test_one_time_budget_uses_its_range(self):
        w = World()
        card = w.account()
        food = w.category()
        w.tx(card.id, 70_00, category_id=food.id, day=date(2026, 4, 5))
        dto = w.budget(food.id, period="one_time", start_date="2026-04-01", end_date="2026-04-10")
        assert (dto.period_start, dto.period_end) == (date(2026, 4, 1), date(2026, 4, 10))
        assert dto.spent.to_minor_units() == 70_00
        assert dto.end_date == date(2026, 4, 10)

    def test_second_budget_for_a_category_rejected(self):
        w = World()
        food = w.category()
        w.budget(food.id)
        with pytest.raises(BudgetAlreadyExistsError) as exc:
            w.budget(food.id, period="weekly")
        assert exc.value.errors == {"category_id": "budget_already_exists"}

    def test_update_may_keep_its_own_category(self):
        w = World()
        food = w.category()
        dto = w.budget(food.id)
        updated = UpdateBudget(w.budgets, w.categories, w.reporter).execute(
            USER, dto.id, UpdateBudgetInput(category_id=food.id, amount_minor=900_00)
        )
        assert updated.amount.to_minor_units() == 900_00

    def test_list(self):
        w = World()
        w.budget(w.category("Еда").id)
        w.budget(w.category("Дом").id)
        assert len(ListBudgets(w.budgets, w.reporter).execute(USER)) == 2
