"""Django ORM implementations of the goals ports."""

from decimal import Decimal
from uuid import UUID

from django.db.models import Sum

from goals.application.ports import GoalContributionRepository, GoalRepository
from goals.domain.entities import Goal, GoalContribution
from goals.infrastructure.mappers import (
    contribution_to_domain,
    contribution_to_orm,
    goal_to_domain,
    goal_to_orm,
)
from goals.infrastructure.orm.models import Goal as GoalORM
from goals.infrastructure.orm.models import GoalContribution as GoalContributionORM
from shared.domain.money import DEFAULT_CURRENCY, Money


class DjangoGoalRepository(GoalRepository):
    def add(self, goal: Goal) -> Goal:
        goal_to_orm(goal).save(force_insert=True)
        return goal

    def get_by_id(self, goal_id: UUID, user_id: UUID) -> Goal | None:
        orm = GoalORM.objects.filter(pk=goal_id, user_id=user_id).first()
        return goal_to_domain(orm) if orm else None

    def list_for_user(self, user_id: UUID) -> list[Goal]:
        return [goal_to_domain(g) for g in GoalORM.objects.filter(user_id=user_id)]

    def update(self, goal: Goal) -> Goal:
        GoalORM.objects.filter(pk=goal.id, user_id=goal.user_id).update(
            name=goal.name,
            target_amount=goal.target_amount.amount,
            deadline=goal.deadline,
            icon=goal.icon,
            color=goal.color,
        )
        return goal

    def delete(self, goal_id: UUID, user_id: UUID) -> bool:
        deleted, _ = GoalORM.objects.filter(pk=goal_id, user_id=user_id).delete()
        return deleted > 0


class DjangoGoalContributionRepository(GoalContributionRepository):
    def add(self, contribution: GoalContribution) -> GoalContribution:
        contribution_to_orm(contribution).save(force_insert=True)
        return contribution

    def list_for_goal(self, goal_id: UUID) -> list[GoalContribution]:
        return [
            contribution_to_domain(c) for c in GoalContributionORM.objects.filter(goal_id=goal_id)
        ]

    def sum_for_goal(self, goal_id: UUID) -> Money:
        row = (
            GoalORM.objects.filter(pk=goal_id)
            .annotate(total=Sum("contributions__amount"))
            .values("currency", "total")
            .first()
        )
        if row is None:
            return Money.zero(DEFAULT_CURRENCY)
        return Money(Decimal(row["total"] or 0), row["currency"])

    def sums_for_goals(self, goal_ids: list[UUID]) -> dict[UUID, Money]:
        rows = (
            GoalContributionORM.objects.filter(goal_id__in=goal_ids)
            .order_by()
            .values("goal_id", "currency")
            .annotate(total=Sum("amount"))
        )
        return {r["goal_id"]: Money(Decimal(r["total"]), r["currency"]) for r in rows}
