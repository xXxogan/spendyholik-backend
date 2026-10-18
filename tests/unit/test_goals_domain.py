from datetime import date
from uuid import uuid4

import pytest

from goals.domain.entities import Goal, GoalContribution
from shared.domain.money import Money
from shared.exceptions import ValidationError

USER = uuid4()
ACCT = uuid4()


class TestGoal:
    def test_creates_goal(self):
        goal = Goal(
            user_id=USER,
            name="Подушка",
            account_id=ACCT,
            target_amount=Money.from_minor_units(100000_00, "RUB"),
        )
        assert goal.initial_amount.to_minor_units() == 0

    def test_rejects_non_positive_target(self):
        with pytest.raises(ValidationError):
            Goal(user_id=USER, name="X", account_id=ACCT, target_amount=Money.zero("RUB"))

    def test_rejects_negative_initial(self):
        with pytest.raises(ValidationError):
            Goal(
                user_id=USER,
                name="X",
                account_id=ACCT,
                target_amount=Money.from_minor_units(100, "RUB"),
                initial_amount=Money.from_minor_units(-1, "RUB"),
            )

    def test_rejects_currency_mismatch(self):
        with pytest.raises(ValidationError):
            Goal(
                user_id=USER,
                name="X",
                account_id=ACCT,
                target_amount=Money.from_minor_units(100, "RUB"),
                initial_amount=Money.from_minor_units(10, "USD"),
            )


class TestGoalContribution:
    def test_creates_contribution(self):
        c = GoalContribution(
            goal_id=uuid4(),
            account_id=ACCT,
            amount=Money.from_minor_units(500_00, "RUB"),
            date=date(2026, 3, 15),
        )
        assert c.amount.is_positive()

    def test_rejects_non_positive(self):
        with pytest.raises(ValidationError):
            GoalContribution(
                goal_id=uuid4(),
                account_id=ACCT,
                amount=Money.zero("RUB"),
                date=date(2026, 3, 15),
            )
