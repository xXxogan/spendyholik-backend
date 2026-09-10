"""Enums for the notifications bounded context."""

from enum import StrEnum


class NotificationType(StrEnum):
    SYSTEM = "system"
    BUDGET_THRESHOLD = "budget_threshold"
    GOAL_PROGRESS = "goal_progress"
    UPCOMING_RECURRING = "upcoming_recurring"
    WEEKLY_REPORT = "weekly_report"
