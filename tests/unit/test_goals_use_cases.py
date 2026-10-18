from datetime import date
from uuid import uuid4

import pytest

from finances.application.dto import CreateAccountInput
from finances.application.use_cases import CreateAccount
from goals.application.dto import ContributeToGoalInput, CreateGoalInput
from goals.application.use_cases import (
    ContributeToGoal,
    CreateGoal,
    ForecastGoal,
    GetGoalDetail,
    ListGoals,
)
from goals.domain.exceptions import GoalNotFoundError
from shared.exceptions import ValidationError
from tests.fakes import (
    FakeClock,
    FakeUnitOfWork,
    InMemoryAccountRepository,
    InMemoryGoalContributionRepository,
    InMemoryGoalRepository,
)

USER = uuid4()


def _account():
    repo = InMemoryAccountRepository()
    dto = CreateAccount(repo).execute(
        USER, CreateAccountInput(name="Счёт", type="debit", currency="RUB")
    )
    return repo, dto.id


class TestCreateGoal:
    def test_creates_goal_with_progress_zero(self):
        accounts, acct_id = _account()
        goals = InMemoryGoalRepository()
        dto = CreateGoal(goals, accounts).execute(
            USER,
            CreateGoalInput(
                name="Подушка", target_amount_minor=100000_00, currency="RUB", account_id=acct_id
            ),
        )
        assert dto.current_amount.to_minor_units() == 0
        assert dto.progress == 0.0

    def test_rejects_mismatched_currency(self):
        accounts, acct_id = _account()
        with pytest.raises(ValidationError):
            CreateGoal(InMemoryGoalRepository(), accounts).execute(
                USER,
                CreateGoalInput(
                    name="X", target_amount_minor=100, currency="USD", account_id=acct_id
                ),
            )


class TestContributeAndProgress:
    def test_current_amount_includes_contributions(self):
        accounts, acct_id = _account()
        goals = InMemoryGoalRepository()
        contributions = InMemoryGoalContributionRepository()
        goal = CreateGoal(goals, accounts).execute(
            USER,
            CreateGoalInput(
                name="Подушка", target_amount_minor=100000_00, currency="RUB", account_id=acct_id
            ),
        )
        ContributeToGoal(goals, contributions, accounts, FakeUnitOfWork()).execute(
            USER,
            goal.id,
            ContributeToGoalInput(
                account_id=acct_id, amount_minor=25000_00, date=date(2026, 3, 15)
            ),
        )
        detail = GetGoalDetail(goals, contributions).execute(USER, goal.id)
        assert detail.current_amount.to_minor_units() == 25000_00
        assert detail.progress == 0.25


class TestForecast:
    def test_forecast_without_contributions_is_none(self):
        accounts, acct_id = _account()
        goals = InMemoryGoalRepository()
        goal = CreateGoal(goals, accounts).execute(
            USER,
            CreateGoalInput(
                name="Подушка", target_amount_minor=100000_00, currency="RUB", account_id=acct_id
            ),
        )
        forecast = ForecastGoal(goals, InMemoryGoalContributionRepository(), FakeClock()).execute(
            USER, goal.id
        )
        assert forecast.projected_completion is None

    def test_forecast_missing_goal_raises(self):
        with pytest.raises(GoalNotFoundError):
            ForecastGoal(
                InMemoryGoalRepository(), InMemoryGoalContributionRepository(), FakeClock()
            ).execute(USER, uuid4())


class TestListGoals:
    def test_lists_goals(self):
        accounts, acct_id = _account()
        goals = InMemoryGoalRepository()
        CreateGoal(goals, accounts).execute(
            USER,
            CreateGoalInput(name="A", target_amount_minor=100, currency="RUB", account_id=acct_id),
        )
        assert len(ListGoals(goals, InMemoryGoalContributionRepository()).execute(USER)) == 1
