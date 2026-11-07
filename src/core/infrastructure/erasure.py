"""Erasing a user's data across bounded contexts ("delete all data")."""

from __future__ import annotations

from uuid import UUID

from accounts.application.ports import UserDataEraser
from debts.infrastructure.orm.models import Debt
from finances.infrastructure.orm.models import Account, Budget, Category, Transaction
from goals.infrastructure.orm.models import Goal
from notifications.infrastructure.orm.models import Notification
from recurring.infrastructure.orm.models import RecurringTransaction


class DjangoUserDataEraser(UserDataEraser):
    def erase(self, user_id: UUID) -> None:
        # Dependents first; goal contributions and debt payments go with their parents.
        for model in (
            Goal,
            Debt,
            RecurringTransaction,
            Budget,
            Transaction,
            Account,
            Category,
            Notification,
        ):
            model.objects.filter(user_id=user_id).delete()
