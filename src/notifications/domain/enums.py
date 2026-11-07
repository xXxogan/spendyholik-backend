"""Enums for the notifications bounded context."""

from enum import StrEnum


class NotificationType(StrEnum):
    """What happened; the client builds the text from the type and the structured fields."""

    BUDGET_ALMOST_SPENT = "budget_almost_spent"
    INCOME_RECEIVED = "income_received"
    RECURRING_TOMORROW = "recurring_tomorrow"
    GOAL_PROGRESS = "goal_progress"
