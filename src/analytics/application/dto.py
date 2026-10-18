"""DTOs for the analytics application layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from shared.domain.money import Money


@dataclass(frozen=True, slots=True)
class BudgetStatusDTO:
    budget_id: UUID
    category_id: UUID
    limit: Money
    spent: Money
    remaining: Money
    ratio: float


@dataclass(frozen=True, slots=True)
class DashboardDTO:
    total_balance: Money
    income_this_month: Money
    expense_this_month: Money
    net_this_month: Money
    budgets: list[BudgetStatusDTO]
    excluded_currencies: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SummaryDTO:
    income: Money
    expense: Money
    net: Money
    excluded_currencies: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CategorySpendingDTO:
    category_id: UUID
    category_name: str
    amount: Money
    ratio: float


@dataclass(frozen=True, slots=True)
class MonthlyTrendPointDTO:
    month: date  # first day of the month
    income: Money
    expense: Money
