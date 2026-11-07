"""Enums for the finances bounded context."""

from enum import StrEnum


class TransactionType(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


class AccountType(StrEnum):
    DEBIT = "debit"
    CASH = "cash"
    SAVINGS = "savings"
    CREDIT = "credit"


class BudgetPeriod(StrEnum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    ONE_TIME = "one_time"


class Granularity(StrEnum):
    """Bucket size of a time series."""

    DAY = "day"
    MONTH = "month"
    YEAR = "year"
