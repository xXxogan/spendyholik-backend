"""Enums for the recurring bounded context."""

from enum import StrEnum


class RecurringFrequency(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
