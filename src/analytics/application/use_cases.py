"""Analytics use cases — aggregate over finances data.

Every amount is reported in the user's base currency; totals in currencies
without a known exchange rate are left out and listed in ``excluded_currencies``.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from dateutil.relativedelta import relativedelta

from accounts.application.ports import ProfileRepository
from analytics.application.currency import CurrencyConverter, base_currency_for
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
    ExchangeRateRepository,
    TransactionRepository,
)
from finances.domain.entities import Budget
from finances.domain.enums import BudgetPeriod, TransactionType
from shared.domain.clock import Clock

#: Upper bound for the monthly trend window.
MAX_TREND_MONTHS = 36


def _budget_window_start(budget: Budget, today: date) -> date | None:
    """First day counted against ``budget`` (``None`` = since the beginning)."""
    if budget.period is BudgetPeriod.WEEKLY:
        return today - timedelta(days=today.weekday())
    if budget.period is BudgetPeriod.ONE_TIME:
        return budget.start_date
    return today.replace(day=1)


class _AnalyticsUseCase:
    def __init__(
        self,
        transactions: TransactionRepository,
        profiles: ProfileRepository,
        rates: ExchangeRateRepository,
    ) -> None:
        self._transactions = transactions
        self._profiles = profiles
        self._rates = rates

    def _converter(self, user_id: UUID) -> CurrencyConverter:
        return CurrencyConverter(self._rates, base_currency_for(self._profiles, user_id))


class GetDashboard(_AnalyticsUseCase):
    def __init__(
        self,
        accounts: AccountRepository,
        transactions: TransactionRepository,
        budgets: BudgetRepository,
        profiles: ProfileRepository,
        rates: ExchangeRateRepository,
        clock: Clock,
    ) -> None:
        super().__init__(transactions, profiles, rates)
        self._accounts = accounts
        self._budgets = budgets
        self._clock = clock

    def execute(self, user_id: UUID) -> DashboardDTO:
        fx = self._converter(user_id)
        today = self._clock.now().date()

        month = self._transactions.totals_by_type(
            user_id, date_from=today.replace(day=1), date_to=today
        )
        income_month = fx.total(month.get(TransactionType.INCOME))
        expense_month = fx.total(month.get(TransactionType.EXPENSE))

        # Total balance: initial balances + all income − all expenses (transfers net to zero).
        all_time = self._transactions.totals_by_type(user_id)
        initial = fx.sum(a.initial_balance for a in self._accounts.list_for_user(user_id))
        total_balance = (
            initial
            + fx.total(all_time.get(TransactionType.INCOME))
            - fx.total(all_time.get(TransactionType.EXPENSE))
        )

        # One aggregate per distinct budget window instead of one per budget.
        active = [b for b in self._budgets.list_for_user(user_id) if b.is_active]
        spent_by_window = {
            start: self._transactions.sum_by_category(
                user_id, type=TransactionType.EXPENSE, date_from=start, date_to=today
            )
            for start in {_budget_window_start(b, today) for b in active}
        }
        budget_statuses = []
        for budget in active:
            window = spent_by_window[_budget_window_start(budget, today)]
            spent = fx.total(window.get(budget.category_id))
            limit = fx.total({budget.amount.currency: budget.amount})
            budget_statuses.append(
                BudgetStatusDTO(
                    budget_id=budget.id,
                    category_id=budget.category_id,
                    limit=limit,
                    spent=spent,
                    remaining=limit - spent,
                    ratio=0.0 if limit.is_zero() else float(spent.amount / limit.amount),
                )
            )

        return DashboardDTO(
            total_balance=total_balance,
            income_this_month=income_month,
            expense_this_month=expense_month,
            net_this_month=income_month - expense_month,
            budgets=budget_statuses,
            excluded_currencies=sorted(fx.excluded),
        )


class GetSummary(_AnalyticsUseCase):
    def execute(
        self, user_id: UUID, date_from: date | None = None, date_to: date | None = None
    ) -> SummaryDTO:
        fx = self._converter(user_id)
        totals = self._transactions.totals_by_type(user_id, date_from=date_from, date_to=date_to)
        income = fx.total(totals.get(TransactionType.INCOME))
        expense = fx.total(totals.get(TransactionType.EXPENSE))
        return SummaryDTO(
            income=income,
            expense=expense,
            net=income - expense,
            excluded_currencies=sorted(fx.excluded),
        )


class GetSpendingByCategory(_AnalyticsUseCase):
    def __init__(
        self,
        transactions: TransactionRepository,
        categories: CategoryRepository,
        profiles: ProfileRepository,
        rates: ExchangeRateRepository,
    ) -> None:
        super().__init__(transactions, profiles, rates)
        self._categories = categories

    def execute(
        self, user_id: UUID, date_from: date | None = None, date_to: date | None = None
    ) -> list[CategorySpendingDTO]:
        fx = self._converter(user_id)
        sums = self._transactions.sum_by_category(
            user_id, type=TransactionType.EXPENSE, date_from=date_from, date_to=date_to
        )
        amounts = {category_id: fx.total(totals) for category_id, totals in sums.items()}
        total = fx.sum(amounts.values())
        names = {c.id: c.name for c in self._categories.list_for_user(user_id)}
        return [
            CategorySpendingDTO(
                category_id=category_id,
                category_name=names.get(category_id, "—"),
                amount=amount,
                ratio=0.0 if total.is_zero() else float(amount.amount / total.amount),
            )
            for category_id, amount in sorted(
                amounts.items(), key=lambda kv: kv[1].amount, reverse=True
            )
        ]


class GetMonthlyTrend(_AnalyticsUseCase):
    def __init__(
        self,
        transactions: TransactionRepository,
        profiles: ProfileRepository,
        rates: ExchangeRateRepository,
        clock: Clock,
    ) -> None:
        super().__init__(transactions, profiles, rates)
        self._clock = clock

    def execute(self, user_id: UUID, months: int = 6) -> list[MonthlyTrendPointDTO]:
        months = min(max(months, 1), MAX_TREND_MONTHS)
        fx = self._converter(user_id)
        current = self._clock.now().date().replace(day=1)
        start = current - relativedelta(months=months - 1)
        totals = self._transactions.monthly_totals(
            user_id, date_from=start, date_to=self._clock.now().date()
        )
        points = []
        for offset in range(months):
            month = start + relativedelta(months=offset)
            points.append(
                MonthlyTrendPointDTO(
                    month=month,
                    income=fx.total(totals.get((month, TransactionType.INCOME))),
                    expense=fx.total(totals.get((month, TransactionType.EXPENSE))),
                )
            )
        return points
