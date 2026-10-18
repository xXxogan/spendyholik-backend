"""ORM ↔ domain mappers for the goals bounded context."""

from decimal import Decimal

from goals.domain.entities import Goal, GoalContribution
from goals.infrastructure.orm.models import Goal as GoalORM
from goals.infrastructure.orm.models import GoalContribution as GoalContributionORM
from shared.domain.money import Money


def goal_to_domain(orm: GoalORM) -> Goal:
    return Goal(
        id=orm.id,
        user_id=orm.user_id,
        name=orm.name,
        target_amount=Money(Decimal(orm.target_amount), orm.currency),
        initial_amount=Money(Decimal(orm.initial_amount), orm.currency),
        account_id=orm.account_id,
        deadline=orm.deadline,
        icon=orm.icon,
        color=orm.color,
    )


def goal_to_orm(goal: Goal) -> GoalORM:
    return GoalORM(
        id=goal.id,
        user_id=goal.user_id,
        name=goal.name,
        target_amount=goal.target_amount.amount,
        initial_amount=goal.initial_amount.amount,
        currency=goal.target_amount.currency,
        account_id=goal.account_id,
        deadline=goal.deadline,
        icon=goal.icon,
        color=goal.color,
    )


def contribution_to_domain(orm: GoalContributionORM) -> GoalContribution:
    return GoalContribution(
        id=orm.id,
        goal_id=orm.goal_id,
        account_id=orm.account_id,
        amount=Money(Decimal(orm.amount), orm.currency),
        date=orm.date,
    )


def contribution_to_orm(c: GoalContribution) -> GoalContributionORM:
    return GoalContributionORM(
        id=c.id,
        goal_id=c.goal_id,
        account_id=c.account_id,
        amount=c.amount.amount,
        currency=c.amount.currency,
        date=c.date,
    )
