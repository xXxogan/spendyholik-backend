"""Use cases for the goals bounded context."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from finances.application.ports import AccountRepository
from finances.domain.exceptions import AccountNotFoundError
from goals.application.dto import (
    ContributeToGoalInput,
    CreateGoalInput,
    GoalContributionDTO,
    GoalDTO,
    GoalForecastDTO,
    UpdateGoalInput,
)
from goals.application.ports import GoalContributionRepository, GoalRepository
from goals.domain.entities import Goal, GoalContribution
from goals.domain.exceptions import GoalNotFoundError
from shared.application.ports import UnitOfWork
from shared.domain.clock import Clock
from shared.domain.money import Money
from shared.exceptions import ValidationError


def _current_amount(goal: Goal, contributions_sum: Money) -> Money:
    return goal.initial_amount + contributions_sum


def _goal_dto(goal: Goal, current: Money) -> GoalDTO:
    progress = 0.0 if goal.target_amount.is_zero() else float(current.amount / goal.target_amount.amount)
    return GoalDTO(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        current_amount=current,
        account_id=goal.account_id,
        deadline=goal.deadline,
        icon=goal.icon,
        color=goal.color,
        progress=min(max(progress, 0.0), 1.0),
    )


class CreateGoal:
    def __init__(self, goals: GoalRepository, accounts: AccountRepository) -> None:
        self._goals = goals
        self._accounts = accounts

    def execute(self, user_id: UUID, data: CreateGoalInput) -> GoalDTO:
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        if account.currency.value != data.currency:
            msg = f"Goal currency must match account currency {account.currency.value}."
            raise ValidationError(msg)
        goal = Goal(
            user_id=user_id,
            name=data.name,
            target_amount=Money.from_minor_units(data.target_amount_minor, data.currency),
            initial_amount=Money.from_minor_units(data.initial_amount_minor, data.currency),
            account_id=data.account_id,
            deadline=data.deadline,
            icon=data.icon,
            color=data.color,
        )
        return _goal_dto(self._goals.add(goal), goal.initial_amount)


class UpdateGoal:
    def __init__(self, goals: GoalRepository, contributions: GoalContributionRepository) -> None:
        self._goals = goals
        self._contributions = contributions

    def execute(self, user_id: UUID, goal_id: UUID, data: UpdateGoalInput) -> GoalDTO:
        goal = self._goals.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        updated = Goal(
            id=goal.id,
            user_id=user_id,
            name=data.name if data.name is not None else goal.name,
            target_amount=(
                goal.target_amount
                if data.target_amount_minor is None
                else Money.from_minor_units(data.target_amount_minor, goal.target_amount.currency)
            ),
            initial_amount=goal.initial_amount,
            account_id=goal.account_id,
            deadline=goal.deadline if data.deadline is None else data.deadline,
            icon=data.icon if data.icon is not None else goal.icon,
            color=data.color if data.color is not None else goal.color,
        )
        saved = self._goals.update(updated)
        return _goal_dto(saved, _current_amount(saved, self._contributions.sum_for_goal(goal_id)))


class ListGoals:
    def __init__(self, goals: GoalRepository, contributions: GoalContributionRepository) -> None:
        self._goals = goals
        self._contributions = contributions

    def execute(self, user_id: UUID) -> list[GoalDTO]:
        return [
            _goal_dto(g, _current_amount(g, self._contributions.sum_for_goal(g.id)))
            for g in self._goals.list_for_user(user_id)
        ]


class GetGoalDetail:
    def __init__(self, goals: GoalRepository, contributions: GoalContributionRepository) -> None:
        self._goals = goals
        self._contributions = contributions

    def execute(self, user_id: UUID, goal_id: UUID) -> GoalDTO:
        goal = self._goals.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        return _goal_dto(goal, _current_amount(goal, self._contributions.sum_for_goal(goal_id)))


class ContributeToGoal:
    def __init__(
        self,
        goals: GoalRepository,
        contributions: GoalContributionRepository,
        accounts: AccountRepository,
        uow: UnitOfWork,
    ) -> None:
        self._goals = goals
        self._contributions = contributions
        self._accounts = accounts
        self._uow = uow

    def execute(self, user_id: UUID, goal_id: UUID, data: ContributeToGoalInput) -> GoalContributionDTO:
        goal = self._goals.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        with self._uow:
            contribution = self._contributions.add(
                GoalContribution(
                    goal_id=goal_id,
                    account_id=data.account_id,
                    amount=Money.from_minor_units(data.amount_minor, goal.target_amount.currency),
                    date=data.date,
                )
            )
        return GoalContributionDTO(
            id=contribution.id,
            goal_id=contribution.goal_id,
            account_id=contribution.account_id,
            amount=contribution.amount,
            date=contribution.date,
        )


class ForecastGoal:
    def __init__(
        self,
        goals: GoalRepository,
        contributions: GoalContributionRepository,
        clock: Clock,
    ) -> None:
        self._goals = goals
        self._contributions = contributions
        self._clock = clock

    def execute(self, user_id: UUID, goal_id: UUID) -> GoalForecastDTO:
        goal = self._goals.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        current = _current_amount(goal, self._contributions.sum_for_goal(goal_id))
        remaining = goal.target_amount - current
        if remaining.is_zero() or remaining.is_negative():
            return GoalForecastDTO(
                goal_id=goal_id,
                remaining=Money.zero(remaining.currency),
                projected_completion=self._clock.now().date(),
            )
        contributions = self._contributions.list_for_goal(goal_id)
        if not contributions:
            return GoalForecastDTO(goal_id=goal_id, remaining=remaining, projected_completion=None)
        oldest = min(c.date for c in contributions)
        newest = max(c.date for c in contributions)
        days_span = max((newest - oldest).days, 1)
        total = sum((c.amount for c in contributions), Money.zero(remaining.currency))
        per_day = total / Decimal(days_span)
        if per_day.is_zero():
            return GoalForecastDTO(goal_id=goal_id, remaining=remaining, projected_completion=None)
        days_needed = int((remaining.amount / per_day.amount).to_integral_value())
        return GoalForecastDTO(
            goal_id=goal_id,
            remaining=remaining,
            projected_completion=self._clock.now().date() + timedelta(days=days_needed),
        )
