"""Use cases for the goals bounded context."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from finances.application.ports import AccountRepository, BalanceReader
from finances.application.use_cases import account_refs, require_funds
from finances.domain.entities import Account
from finances.domain.exceptions import AccountArchivedError, AccountNotFoundError
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
from goals.domain.exceptions import GoalNotFoundError, GoalTargetExceededError
from shared.application.patch import apply_patch
from shared.application.ports import UnitOfWork
from shared.domain.clock import Clock
from shared.domain.money import Money
from shared.exceptions import ValidationError


def _current_amount(goal: Goal, contributions_sum: Money | None) -> Money:
    return (
        goal.initial_amount
        if contributions_sum is None
        else goal.initial_amount + contributions_sum
    )


def _goal_dto(goal: Goal, current: Money) -> GoalDTO:
    progress = (
        0.0 if goal.target_amount.is_zero() else float(current.amount / goal.target_amount.amount)
    )
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


def _contribution_dto(c: GoalContribution, refs: dict | None = None) -> GoalContributionDTO:
    return GoalContributionDTO(
        id=c.id,
        goal_id=c.goal_id,
        account_id=c.account_id,
        amount=c.amount,
        date=c.date,
        account=(refs or {}).get(c.account_id),
    )


def _funding_account(
    accounts: AccountRepository, user_id: UUID, account_id: UUID, currency: str
) -> Account:
    account = accounts.get_by_id(account_id, user_id)
    if account is None:
        raise AccountNotFoundError(account_id)
    if account.is_archived:
        raise AccountArchivedError
    if account.currency.value != currency:
        msg = f"Account currency must match goal currency {currency}."
        raise ValidationError(msg, field="account_id", field_code="currency_mismatch")
    return account


class CreateGoal:
    """Create a goal; a non-zero initial amount is its first contribution.

    That contribution leaves the given account like any other, so it needs
    ``account_id`` and enough money there.
    """

    def __init__(
        self,
        goals: GoalRepository,
        contributions: GoalContributionRepository,
        accounts: AccountRepository,
        balances: BalanceReader,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._goals = goals
        self._contributions = contributions
        self._accounts = accounts
        self._balances = balances
        self._uow = uow
        self._clock = clock

    def execute(self, user_id: UUID, data: CreateGoalInput) -> GoalDTO:
        target = Money.from_minor_units(data.target_amount_minor, data.currency)
        initial = Money.from_minor_units(data.initial_amount_minor, data.currency)
        if initial > target:
            raise GoalTargetExceededError(field="initial_amount_minor")
        account = None
        if data.account_id is not None:
            account = _funding_account(self._accounts, user_id, data.account_id, data.currency)
        elif initial.is_positive():
            msg = "An initial amount needs the account it is taken from."
            raise ValidationError(msg, field="account_id", field_code="required")
        if account is not None and initial.is_positive():
            require_funds(self._balances, account, initial, "initial_amount_minor")
        goal = Goal(
            user_id=user_id,
            name=data.name,
            target_amount=target,
            initial_amount=Money.zero(data.currency),
            account_id=data.account_id,
            deadline=data.deadline,
            icon=data.icon,
            color=data.color,
        )
        with self._uow:
            self._goals.add(goal)
            if account is not None and initial.is_positive():
                self._contributions.add(
                    GoalContribution(
                        goal_id=goal.id,
                        account_id=account.id,
                        amount=initial,
                        date=self._clock.now().date(),
                    )
                )
        return _goal_dto(goal, initial)


class UpdateGoal:
    def __init__(self, goals: GoalRepository, contributions: GoalContributionRepository) -> None:
        self._goals = goals
        self._contributions = contributions

    def execute(self, user_id: UUID, goal_id: UUID, data: UpdateGoalInput) -> GoalDTO:
        goal = self._goals.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        currency = goal.target_amount.currency
        updated = apply_patch(
            goal,
            data,
            fields={
                "target_amount_minor": (
                    "target_amount",
                    lambda m: Money.from_minor_units(m, currency),
                ),
            },
            nullable={"deadline"},
        )
        saved = self._goals.update(updated)
        return _goal_dto(saved, _current_amount(saved, self._contributions.sum_for_goal(goal_id)))


class ListGoals:
    def __init__(self, goals: GoalRepository, contributions: GoalContributionRepository) -> None:
        self._goals = goals
        self._contributions = contributions

    def execute(self, user_id: UUID) -> list[GoalDTO]:
        goals = self._goals.list_for_user(user_id)
        sums = self._contributions.sums_for_goals([g.id for g in goals])
        return [_goal_dto(g, _current_amount(g, sums.get(g.id))) for g in goals]


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
        balances: BalanceReader,
        uow: UnitOfWork,
    ) -> None:
        self._goals = goals
        self._contributions = contributions
        self._accounts = accounts
        self._balances = balances
        self._uow = uow

    def execute(
        self, user_id: UUID, goal_id: UUID, data: ContributeToGoalInput
    ) -> GoalContributionDTO:
        goal = self._goals.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        currency = goal.target_amount.currency
        account = _funding_account(self._accounts, user_id, data.account_id, currency)
        amount = Money.from_minor_units(data.amount_minor, currency)
        current = _current_amount(goal, self._contributions.sum_for_goal(goal_id))
        if amount > goal.target_amount - current:
            raise GoalTargetExceededError
        require_funds(self._balances, account, amount, "amount_minor")
        with self._uow:
            contribution = self._contributions.add(
                GoalContribution(
                    goal_id=goal_id, account_id=account.id, amount=amount, date=data.date
                )
            )
        return _contribution_dto(contribution, account_refs(self._accounts, user_id))


class ListGoalContributions:
    """A goal's contributions, newest first, with the account each came from."""

    def __init__(
        self,
        goals: GoalRepository,
        contributions: GoalContributionRepository,
        accounts: AccountRepository,
    ) -> None:
        self._goals = goals
        self._contributions = contributions
        self._accounts = accounts

    def execute(self, user_id: UUID, goal_id: UUID) -> list[GoalContributionDTO]:
        if self._goals.get_by_id(goal_id, user_id) is None:
            raise GoalNotFoundError(goal_id)
        items = self._contributions.list_for_goal(goal_id)
        refs = account_refs(self._accounts, user_id)
        items.sort(key=lambda c: c.date, reverse=True)
        return [_contribution_dto(c, refs) for c in items]


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


class DeleteGoal:
    def __init__(self, goals: GoalRepository) -> None:
        self._goals = goals

    def execute(self, user_id: UUID, goal_id: UUID) -> None:
        if not self._goals.delete(goal_id, user_id):
            raise GoalNotFoundError(goal_id)
