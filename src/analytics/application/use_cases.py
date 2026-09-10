"""Analytics use cases — aggregate over finances data."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from analytics.application.dto import (
    BudgetStatusDTO,
    CategorySpendingDTO,
    DashboardDTO,
    MonthlyTrendPointDTO,
    SummaryDTO,
)
from finances.application.ports import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)
from finances.domain.enums import BudgetPeriod, TransactionType
from shared.domain.clock import Clock
from shared.domain.money import DEFAULT_CURRENCY, Money


def _zero(currency: str = DEFAULT_CURRENCY) -> Money:
    return Money.zero(currency)


def _first_day_of_month(d: date) -> date:
    return d.replace(day=1)


class GetDashboard:
    def __init__(
        self,
        accounts: AccountRepository,
        transactions: TransactionRepository,
        budgets: BudgetRepository,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._transactions = transactions
        self._budgets = budgets
        self._clock = clock

    def execute(self, user_id: UUID) -> DashboardDTO:
        today = self._clock.now().date()
        month_start = _first_day_of_month(today)

        income_month = self._transactions.total_amount(
            user_id, type=TransactionType.INCOME, date_from=month_start, date_to=today
        ) or _zero()
        expense_month = self._transactions.total_amount(
            user_id, type=TransactionType.EXPENSE, date_from=month_start, date_to=today
        ) or _zero()

        # Total balance: initial balances + all income − all expenses (transfers net to zero).
        initial = sum(
            (a.initial_balance for a in self._accounts.list_for_user(user_id)),
            _zero(),
        )
        total_income = self._transactions.total_amount(user_id, type=TransactionType.INCOME) or _zero()
        total_expense = self._transactions.total_amount(user_id, type=TransactionType.EXPENSE) or _zero()
        total_balance = initial + total_income - total_expense

        budget_statuses: list[BudgetStatusDTO] = []
        for budget in self._budgets.list_for_user(user_id):
            if not budget.is_active:
                continue
            spent = self._transactions.total_amount(
                user_id,
                type=TransactionType.EXPENSE,
                category_id=budget.category_id,
                date_from=month_start,
                date_to=today,
            ) or _zero(budget.amount.currency)
            remaining = budget.amount - spent
            ratio = 0.0 if budget.amount.is_zero() else float(spent.amount / budget.amount.amount)
            budget_statuses.append(
                BudgetStatusDTO(
                    budget_id=budget.id,
                    category_id=budget.category_id,
                    limit=budget.amount,
                    spent=spent,
                    remaining=remaining,
                    ratio=ratio,
                )
            )

        return DashboardDTO(
            total_balance=total_balance,
            income_this_month=income_month,
            expense_this_month=expense_month,
            net_this_month=income_month - expense_month,
            budgets=budget_statuses,
        )


class GetSummary:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, date_from: date | None = None, date_to: date | None = None) -> SummaryDTO:
        income = self._transactions.total_amount(
            user_id, type=TransactionType.INCOME, date_from=date_from, date_to=date_to
        ) or _zero()
        expense = self._transactions.total_amount(
            user_id, type=TransactionType.EXPENSE, date_from=date_from, date_to=date_to
        ) or _zero()
        return SummaryDTO(income=income, expense=expense, net=income - expense)


class GetSpendingByCategory:
    def __init__(self, transactions: TransactionRepository, categories: CategoryRepository) -> None:
        self._transactions = transactions
        self._categories = categories

    def execute(self, user_id: UUID, date_from: date | None = None, date_to: date | None = None) -> list[CategorySpendingDTO]:
        sums = self._transactions.sum_by_category(
            user_id, type=TransactionType.EXPENSE, date_from=date_from, date_to=date_to
        )
        total = sum(sums.values(), _zero()) if sums else _zero()
        categories = {c.id: c for c in self._categories.list_for_user(user_id)}
        result = []
        for category_id, amount in sorted(sums.items(), key=lambda kv: kv[1].amount, reverse=True):
            name = categories.get(category_id)
            result.append(
                CategorySpendingDTO(
                    category_id=category_id,
                    category_name=name.name if name else "—",
                    amount=amount,
                    ratio=0.0 if total.is_zero() else float(amount.amount / total.amount),
                )
            )
        return result


class GetMonthlyTrend:
    def __init__(self, transactions: TransactionRepository, clock: Clock) -> None:
        self._transactions = transactions
        self._clock = clock

    def execute(self, user_id: UUID, months: int = 6) -> list[MonthlyTrendPointDTO]:
        from dateutil.relativedelta import relativedelta

        today = self._clock.now().date()
        start = _first_day_of_month(today - relativedelta(months=months - 1))
        income = dict(self._transactions.monthly_totals(
            user_id, type=TransactionType.INCOME, date_from=start, date_to=today
        ))
        expense = dict(self._transactions.monthly_totals(
            user_id, type=TransactionType.EXPENSE, date_from=start, date_to=today
        ))
        points = []
        cursor = start
        while cursor <= _first_day_of_month(today):
            points.append(
                MonthlyTrendPointDTO(
                    month=cursor,
                    income=income.get(cursor, _zero()),
                    expense=expense.get(cursor, _zero()),
                )
            )
            cursor = cursor + relativedelta(months=1)
        return points
