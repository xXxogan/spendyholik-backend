"""BK-3: real exchange rates — provider parsing, refresh, cross rates, budgets in base."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounts.domain.entities import Profile
from finances.application.currency import CurrencyConverter
from finances.application.dto import (
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
    UpdateBudgetInput,
)
from finances.application.use_cases import (
    BudgetReporter,
    CreateAccount,
    CreateBudget,
    CreateCategory,
    CreateTransaction,
    RefreshExchangeRates,
    UpdateBudget,
)
from finances.domain.entities import ExchangeRate
from shared.application.ports import RatesSnapshot
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money
from shared.exceptions import ExchangeRatesUnavailableError
from shared.infrastructure.gateways import parse_open_er_api
from tests.fakes import (
    FakeClock,
    InMemoryAccountRepository,
    InMemoryBudgetRepository,
    InMemoryCategoryRepository,
    InMemoryExchangeRateRepository,
    InMemoryProfileRepository,
    InMemoryTransactionRepository,
    StubExchangeRateProvider,
)

USER = uuid4()
DAY = date(2026, 11, 7)


def _usd_rates(rates: dict[str, str]) -> InMemoryExchangeRateRepository:
    repo = InMemoryExchangeRateRepository()
    snapshot = RatesSnapshot("USD", DAY, {k: Decimal(v) for k, v in rates.items()})
    RefreshExchangeRates(StubExchangeRateProvider(snapshot), repo, "USD").execute()
    return repo


class TestProviderAnswer:
    def test_parses_rates_and_skips_junk(self):
        snapshot = parse_open_er_api(
            {
                "result": "success",
                "base_code": "USD",
                "time_last_update_unix": 1794009751,
                "rates": {"USD": 1, "RUB": 81.69, "EUR": "0.896", "XX1": 3, "BAD": "x", "ZRO": 0},
            },
            "USD",
        )
        assert snapshot.date == DAY
        assert snapshot.rates == {"RUB": Decimal("81.69"), "EUR": Decimal("0.896")}

    def test_error_answer_raises(self):
        with pytest.raises(ExchangeRatesUnavailableError):
            parse_open_er_api({"result": "error", "error-type": "unsupported-code"}, "USD")


class TestRefresh:
    def test_stores_and_replaces_the_days_rates(self):
        repo = _usd_rates({"RUB": "80"})
        snapshot = RatesSnapshot("USD", DAY, {"RUB": Decimal("82")})
        assert RefreshExchangeRates(StubExchangeRateProvider(snapshot), repo, "USD").execute() == 1
        assert repo.get_latest(CurrencyCode("USD"), CurrencyCode("RUB")).rate == Decimal("82")
        assert len(repo._rates) == 1

    def test_provider_failure_propagates(self):
        provider = StubExchangeRateProvider(error=ExchangeRatesUnavailableError("down"))
        with pytest.raises(ExchangeRatesUnavailableError):
            RefreshExchangeRates(provider, InMemoryExchangeRateRepository(), "USD").execute()


class TestConverter:
    def test_inverse_of_a_usd_rate(self):
        fx = CurrencyConverter(_usd_rates({"RUB": "80"}), "USD")
        assert fx.total({"RUB": Money(Decimal("800"), "RUB")}) == Money(Decimal("10"), "USD")

    def test_cross_rate_through_usd(self):
        fx = CurrencyConverter(_usd_rates({"RUB": "80", "EUR": "0.8"}), "RUB")
        # 10 EUR = 12.5 USD = 1000 RUB
        assert fx.total({"EUR": Money(Decimal("10"), "EUR")}) == Money(Decimal("1000"), "RUB")
        assert fx.excluded == set()

    def test_unknown_currency_is_excluded(self):
        fx = CurrencyConverter(_usd_rates({"RUB": "80"}), "RUB")
        assert fx.total({"KZT": Money(Decimal("10"), "KZT")}).is_zero()
        assert fx.excluded == {"KZT"}

    def test_latest_date_wins(self):
        repo = _usd_rates({"RUB": "80"})
        repo.add(
            ExchangeRate(CurrencyCode("USD"), CurrencyCode("RUB"), Decimal("90"), date(2026, 11, 8))
        )
        fx = CurrencyConverter(repo, "USD")
        assert fx.total({"RUB": Money(Decimal("90"), "RUB")}) == Money(Decimal("1"), "USD")


class TestBudgetsInBaseCurrency:
    def _world(self, rates):
        profiles = InMemoryProfileRepository()
        profiles.add(Profile(user_id=USER, base_currency=CurrencyCode("RUB")))
        accounts = InMemoryAccountRepository()
        categories = InMemoryCategoryRepository()
        transactions = InMemoryTransactionRepository(accounts, categories)
        budgets = InMemoryBudgetRepository()
        reporter = BudgetReporter(transactions, categories, rates, FakeClock(DAY), profiles)
        food = CreateCategory(categories).execute(
            USER, CreateCategoryInput(name="Еда", type="expense")
        )
        usd = CreateAccount(accounts).execute(
            USER, CreateAccountInput(name="USD", type="debit", currency="USD")
        )
        CreateTransaction(accounts, categories, transactions).execute(
            USER,
            CreateTransactionInput(
                account_id=usd.id, type="expense", amount_minor=10_00, date=DAY, category_id=food.id
            ),
        )
        budget = CreateBudget(budgets, categories, profiles, reporter).execute(
            USER, CreateBudgetInput(category_id=food.id, amount_minor=5000_00)
        )
        return profiles, budgets, categories, reporter, budget

    def test_foreign_spending_is_converted(self):
        *_, budget = self._world(_usd_rates({"RUB": "80"}))
        assert budget.amount == Money(Decimal("5000"), "RUB")
        assert budget.spent == Money(Decimal("800"), "RUB")

    def test_after_a_base_change_the_limit_is_shown_in_the_new_base(self):
        profiles, budgets, categories, reporter, budget = self._world(_usd_rates({"RUB": "80"}))
        profiles.update(Profile(user_id=USER, base_currency=CurrencyCode("USD")))
        [dto] = reporter.report(USER, budgets.list_for_user(USER))
        assert (dto.amount, dto.spent) == (
            Money(Decimal("62.5"), "USD"),
            Money(Decimal("10"), "USD"),
        )
        updated = UpdateBudget(budgets, categories, reporter, profiles).execute(
            USER, budget.id, UpdateBudgetInput(amount_minor=100_00)
        )
        assert updated.amount == Money(Decimal("100"), "USD")

    def test_without_a_rate_the_budget_keeps_its_currency(self):
        profiles, budgets, _, reporter, _ = self._world(InMemoryExchangeRateRepository())
        profiles.update(Profile(user_id=USER, base_currency=CurrencyCode("EUR")))
        [dto] = reporter.report(USER, budgets.list_for_user(USER))
        assert dto.amount == Money(Decimal("5000"), "RUB")
