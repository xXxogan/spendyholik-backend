"""When the server creates notifications (B-19).

* ``budget_almost_spent`` — an expense change takes an active budget's
  spending (with subcategories) to :data:`BUDGET_THRESHOLD` or more; once per
  budget and period.
* ``income_received`` — a new income transaction (also from a template).
* ``goal_progress`` — a contribution crosses 50, 75 or 100 % of a goal; once
  per goal and threshold (the highest one crossed).
* ``recurring_tomorrow`` — a daily job, for active templates due tomorrow.

Each kind is muted by the profile's ``notify_budget`` / ``notify_income`` /
``notify_goal`` / ``notify_recurring``. A failure is logged and never undoes
the write that triggered it.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from accounts.application.ports import ProfileRepository
from finances.application.ports import (
    BudgetRepository,
    CategoryRepository,
    TransactionObserver,
)
from finances.application.use_cases import BudgetReporter, descendant_ids
from finances.domain.entities import Transaction
from finances.domain.enums import TransactionType
from goals.application.ports import GoalObserver
from notifications.application.ports import NotificationRepository
from notifications.domain.entities import Notification
from notifications.domain.enums import NotificationType
from recurring.application.ports import RecurringTransactionRepository
from shared.application.ports import UnitOfWork
from shared.domain.clock import Clock
from shared.domain.money import Money

logger = logging.getLogger(__name__)

BUDGET_THRESHOLD = 0.8
GOAL_THRESHOLDS = (50, 75, 100)
#: Largest ``percent`` the column holds (a huge overspend is capped, not lost).
MAX_PERCENT = 32767

_FLAG = {
    NotificationType.BUDGET_ALMOST_SPENT: "notify_budget",
    NotificationType.INCOME_RECEIVED: "notify_income",
    NotificationType.GOAL_PROGRESS: "notify_goal",
    NotificationType.RECURRING_TOMORROW: "notify_recurring",
}


class Notifier:
    def __init__(self, notifications: NotificationRepository, profiles: ProfileRepository) -> None:
        self._notifications = notifications
        self._profiles = profiles

    def notify(
        self,
        user_id: UUID,
        type: NotificationType,
        *,
        key: str,
        subject: str = "",
        amount: Money | None = None,
        percent: int | None = None,
    ) -> bool:
        """Create the notification unless muted or already sent for ``key``."""
        profile = self._profiles.get_by_user(user_id)
        if profile is not None and not getattr(profile, _FLAG[type]):
            return False
        return self._notifications.add_once(
            Notification(
                user_id=user_id,
                type=type,
                subject=subject,
                amount_minor=amount.to_minor_units() if amount is not None else None,
                currency=amount.currency if amount is not None else "",
                percent=percent,
            ),
            key,
        )


class TransactionNotifications(TransactionObserver):
    """Runs in its own unit of work (a savepoint inside the caller's): a failed
    query is rolled back alone and cannot poison the caller's transaction."""

    def __init__(
        self,
        notifier: Notifier,
        budgets: BudgetRepository,
        categories: CategoryRepository,
        reporter: BudgetReporter,
        uow: UnitOfWork,
    ) -> None:
        self._notifier = notifier
        self._budgets = budgets
        self._categories = categories
        self._reporter = reporter
        self._uow = uow

    def changed(self, user_id, before, after) -> None:
        try:
            with self._uow:
                if after is None:
                    return  # a deletion only lowers spending
                if before is None and after.type is TransactionType.INCOME:
                    self._income(user_id, after)
                if after.type is TransactionType.EXPENSE and after.category_id:
                    self._budgets_reached(user_id, after)
        except Exception:
            logger.exception("Notifications for a transaction change failed")

    def _income(self, user_id: UUID, tx: Transaction) -> None:
        subject = tx.title
        if not subject and tx.category_id is not None:
            category = self._categories.get_by_id(tx.category_id, user_id)
            subject = category.name if category else ""
        self._notifier.notify(
            user_id,
            NotificationType.INCOME_RECEIVED,
            key=f"income:{tx.id}",
            subject=subject,
            amount=tx.amount,
        )

    def _budgets_reached(self, user_id: UUID, tx: Transaction) -> None:
        categories = self._categories.list_for_user(user_id)
        affected = [
            b
            for b in self._budgets.list_for_user(user_id)
            if b.is_active and tx.category_id in descendant_ids(categories, b.category_id)
        ]
        for budget in self._reporter.report(user_id, affected):
            # Only an expense dated inside the reported period can push it up.
            if budget.period_start is not None and tx.date < budget.period_start:
                continue
            if budget.period_end is not None and tx.date > budget.period_end:
                continue
            if budget.amount.is_zero():
                continue
            ratio = float(budget.spent.amount / budget.amount.amount)
            if ratio < BUDGET_THRESHOLD:
                continue
            self._notifier.notify(
                user_id,
                NotificationType.BUDGET_ALMOST_SPENT,
                key=f"budget:{budget.id}:{budget.period_start}",
                subject=budget.category.name,
                amount=budget.spent,
                percent=min(int(ratio * 100), MAX_PERCENT),
            )


class GoalNotifications(GoalObserver):
    def __init__(self, notifier: Notifier, uow: UnitOfWork) -> None:
        self._notifier = notifier
        self._uow = uow

    def progressed(self, user_id, goal, before: Money, after: Money) -> None:
        try:
            with self._uow:
                self._progressed(user_id, goal, before, after)
        except Exception:
            logger.exception("Notification for goal progress failed")

    def _progressed(self, user_id, goal, before: Money, after: Money) -> None:
        target = goal.target_amount.amount
        if target <= 0:
            return
        was, now = before.amount * 100 / target, after.amount * 100 / target
        crossed = [t for t in GOAL_THRESHOLDS if was < t <= now]
        if not crossed:
            return
        self._notifier.notify(
            user_id,
            NotificationType.GOAL_PROGRESS,
            key=f"goal:{goal.id}:{crossed[-1]}",
            subject=goal.name,
            amount=after,
            percent=crossed[-1],
        )


class NotifyUpcomingRecurring:
    """Daily: one ``recurring_tomorrow`` per active template due tomorrow."""

    def __init__(
        self, recurring: RecurringTransactionRepository, notifier: Notifier, clock: Clock
    ) -> None:
        self._recurring = recurring
        self._notifier = notifier
        self._clock = clock

    def execute(self) -> int:
        tomorrow = self._clock.now().date() + timedelta(days=1)
        sent = 0
        for template in self._recurring.list_runs_on(tomorrow):
            try:
                sent += self._notifier.notify(
                    template.user_id,
                    NotificationType.RECURRING_TOMORROW,
                    key=f"recurring:{template.id}:{tomorrow}",
                    subject=template.name,
                    amount=template.amount,
                )
            except Exception:
                logger.exception("Recurring reminder for %s failed", template.id)
        return sent
