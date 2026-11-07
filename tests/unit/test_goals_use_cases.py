from datetime import date
from uuid import uuid4

import pytest

from finances.application.dto import CreateAccountInput
from finances.application.use_cases import CreateAccount, GetAccountDetail
from finances.domain.exceptions import InsufficientFundsError
from goals.application.dto import ContributeToGoalInput, CreateGoalInput
from goals.application.use_cases import (
    ContributeToGoal,
    CreateGoal,
    ForecastGoal,
    GetGoalDetail,
    ListGoalContributions,
    ListGoals,
)
from goals.domain.exceptions import GoalNotFoundError, GoalTargetExceededError
from shared.exceptions import ValidationError
from tests.fakes import (
    FakeClock,
    FakeUnitOfWork,
    InMemoryAccountRepository,
    InMemoryBalanceReader,
    InMemoryGoalContributionRepository,
    InMemoryGoalRepository,
)

USER = uuid4()
TODAY = date(2026, 3, 15)


class World:
    def __init__(self, initial_minor: int = 50000_00) -> None:
        self.accounts = InMemoryAccountRepository()
        self.goals = InMemoryGoalRepository()
        self.contributions = InMemoryGoalContributionRepository()
        self.balances = InMemoryBalanceReader(contributions=self.contributions)
        self.account_id = (
            CreateAccount(self.accounts)
            .execute(
                USER,
                CreateAccountInput(
                    name="Счёт",
                    type="debit",
                    currency="RUB",
                    initial_balance_minor=initial_minor,
                ),
            )
            .id
        )

    def create(self, **fields):
        data = {"name": "Подушка", "target_amount_minor": 100000_00, "currency": "RUB"} | fields
        return CreateGoal(
            self.goals,
            self.contributions,
            self.accounts,
            self.balances,
            FakeUnitOfWork(),
            FakeClock(TODAY),
        ).execute(USER, CreateGoalInput.model_validate(data))

    def contribute(self, goal_id, amount_minor, day=TODAY):
        return ContributeToGoal(
            self.goals, self.contributions, self.accounts, self.balances, FakeUnitOfWork()
        ).execute(
            USER,
            goal_id,
            ContributeToGoalInput(account_id=self.account_id, amount_minor=amount_minor, date=day),
        )

    def detail(self, goal_id):
        return GetGoalDetail(self.goals, self.contributions).execute(USER, goal_id)

    def balance(self) -> int:
        account = GetAccountDetail(self.accounts, self.balances).execute(USER, self.account_id)
        return account.balance.to_minor_units()


class TestCreateGoal:
    def test_creates_goal_without_an_account(self):
        dto = World().create()
        assert dto.account_id is None
        assert dto.current_amount.to_minor_units() == 0
        assert dto.progress == 0.0

    def test_rejects_mismatched_currency(self):
        w = World()
        with pytest.raises(ValidationError):
            w.create(target_amount_minor=100, currency="USD", account_id=w.account_id)

    def test_initial_amount_is_a_contribution_from_the_account(self):
        w = World()
        dto = w.create(account_id=w.account_id, initial_amount_minor=10000_00)
        assert dto.current_amount.to_minor_units() == 10000_00
        assert w.balance() == 40000_00
        history = ListGoalContributions(w.goals, w.contributions, w.accounts).execute(USER, dto.id)
        assert [c.amount.to_minor_units() for c in history] == [10000_00]
        assert history[0].date == TODAY

    def test_initial_amount_needs_an_account(self):
        with pytest.raises(ValidationError) as exc:
            World().create(initial_amount_minor=100_00)
        assert exc.value.errors == {"account_id": "required"}

    def test_initial_amount_needs_funds(self):
        w = World(initial_minor=100_00)
        with pytest.raises(InsufficientFundsError):
            w.create(account_id=w.account_id, initial_amount_minor=200_00)

    def test_initial_amount_above_target_rejected(self):
        w = World()
        with pytest.raises(GoalTargetExceededError):
            w.create(
                account_id=w.account_id, target_amount_minor=100_00, initial_amount_minor=200_00
            )


class TestContributeAndProgress:
    def test_current_amount_includes_contributions(self):
        w = World()
        goal = w.create()
        w.contribute(goal.id, 25000_00)
        detail = w.detail(goal.id)
        assert detail.current_amount.to_minor_units() == 25000_00
        assert detail.progress == 0.25

    def test_contribution_leaves_the_account(self):
        w = World()
        goal = w.create()
        w.contribute(goal.id, 25000_00)
        assert w.balance() == 25000_00

    def test_contribution_needs_funds(self):
        w = World(initial_minor=100_00)
        goal = w.create()
        with pytest.raises(InsufficientFundsError) as exc:
            w.contribute(goal.id, 200_00)
        assert exc.value.errors == {"amount_minor": "insufficient_funds"}

    def test_contribution_above_what_is_left_rejected(self):
        w = World(initial_minor=200000_00)
        goal = w.create()
        w.contribute(goal.id, 90000_00)
        with pytest.raises(GoalTargetExceededError):
            w.contribute(goal.id, 10000_01)

    def test_contributions_are_listed_newest_first(self):
        w = World()
        goal = w.create()
        w.contribute(goal.id, 100_00, date(2026, 3, 1))
        w.contribute(goal.id, 200_00, date(2026, 3, 10))
        history = ListGoalContributions(w.goals, w.contributions, w.accounts).execute(USER, goal.id)
        assert [c.amount.to_minor_units() for c in history] == [200_00, 100_00]
        assert history[0].account.name == "Счёт"


class TestForecast:
    def test_forecast_without_contributions_is_none(self):
        w = World()
        goal = w.create()
        forecast = ForecastGoal(w.goals, w.contributions, FakeClock()).execute(USER, goal.id)
        assert forecast.projected_completion is None

    def test_forecast_missing_goal_raises(self):
        with pytest.raises(GoalNotFoundError):
            ForecastGoal(
                InMemoryGoalRepository(), InMemoryGoalContributionRepository(), FakeClock()
            ).execute(USER, uuid4())


class TestListGoals:
    def test_lists_goals(self):
        w = World()
        w.create(name="A", target_amount_minor=100)
        assert len(ListGoals(w.goals, w.contributions).execute(USER)) == 1
