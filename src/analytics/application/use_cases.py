"""Analytics use cases — aggregate over finances data.

Every amount is reported in the user's base currency; totals in currencies
without a known exchange rate are left out and listed in ``excluded_currencies``.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from dateutil.relativedelta import relativedelta

from accounts.application.ports import ProfileRepository
from analytics.application.dto import (
    BudgetStatusDTO,
    CategorySpendingDTO,
    DashboardDTO,
    MonthlyTrendPointDTO,
    SummaryDTO,
    TrendPointDTO,
)
from finances.application.currency import CurrencyConverter, base_currency_for
from finances.application.ports import (
    AccountRepository,
    BalanceReader,
    BudgetRepository,
    CategoryRepository,
    ExchangeRateRepository,
    TransactionRepository,
)
from finances.application.use_cases import (
    category_ref,
    current_balance,
    descendant_ids,
    merge_totals,
)
from finances.domain.enums import Granularity, TransactionType
from shared.domain.clock import Clock
from shared.exceptions import ValidationError

#: Upper bound for the monthly trend window.
MAX_TREND_MONTHS = 36
#: Upper bound for the number of points of a trend.
MAX_TREND_POINTS = 400

_STEP = {
    Granularity.DAY: relativedelta(days=1),
    Granularity.MONTH: relativedelta(months=1),
    Granularity.YEAR: relativedelta(years=1),
}


def _bucket_start(day: date, granularity: Granularity) -> date:
    if granularity is Granularity.MONTH:
        return day.replace(day=1)
    if granularity is Granularity.YEAR:
        return day.replace(month=1, day=1)
    return day


def _default_trend_start(today: date, granularity: Granularity) -> date:
    """A week of days, half a year of months or three years."""
    if granularity is Granularity.DAY:
        return today - timedelta(days=6)
    if granularity is Granularity.MONTH:
        return today.replace(day=1) - relativedelta(months=5)
    return today.replace(month=1, day=1) - relativedelta(years=2)


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
        balances: BalanceReader,
        categories: CategoryRepository,
    ) -> None:
        super().__init__(transactions, profiles, rates)
        self._accounts = accounts
        self._budgets = budgets
        self._clock = clock
        self._balances = balances
        self._categories = categories

    def execute(self, user_id: UUID) -> DashboardDTO:
        fx = self._converter(user_id)
        today = self._clock.now().date()

        month = self._transactions.totals_by_type(
            user_id, date_from=today.replace(day=1), date_to=today
        )
        income_month = fx.total(month.get(TransactionType.INCOME))
        expense_month = fx.total(month.get(TransactionType.EXPENSE))

        # Total balance: the sum of the current balances of the live accounts.
        accounts = self._accounts.list_for_user(user_id)
        deltas = self._balances.deltas(user_id, [a.id for a in accounts])
        total_balance = fx.sum(current_balance(a, deltas.get(a.id)) for a in accounts)

        # One aggregate per distinct budget window instead of one per budget.
        active = [b for b in self._budgets.list_for_user(user_id) if b.is_active]
        categories = self._categories.list_for_user(user_id) if active else []
        spent_by_window = {
            window: self._transactions.sum_by_category(
                user_id, type=TransactionType.EXPENSE, date_from=window[0], date_to=window[1]
            )
            for window in {b.period_bounds(today) for b in active}
        }
        budget_statuses = []
        for budget in active:
            window = spent_by_window[budget.period_bounds(today)]
            ids = descendant_ids(categories, budget.category_id)
            spent = fx.total(merge_totals(window.get(i) for i in ids))
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
        """Expenses per top-level category; subcategories roll up into their root."""
        fx = self._converter(user_id)
        sums = self._transactions.sum_by_category(
            user_id, type=TransactionType.EXPENSE, date_from=date_from, date_to=date_to
        )
        by_id = {c.id: c for c in self._categories.list_for_user(user_id)}
        by_root: dict[UUID, list] = {}
        for category_id, totals in sums.items():
            by_root.setdefault(_root_of(by_id, category_id), []).append(totals)
        amounts = {root: fx.total(merge_totals(parts)) for root, parts in by_root.items()}
        total = fx.sum(amounts.values())
        result = []
        for category_id, amount in sorted(
            amounts.items(), key=lambda kv: kv[1].amount, reverse=True
        ):
            category = by_id.get(category_id)
            result.append(
                CategorySpendingDTO(
                    category_id=category_id,
                    category_name=category.name if category else "—",
                    amount=amount,
                    ratio=0.0 if total.is_zero() else float(amount.amount / total.amount),
                    category=category_ref(category) if category else None,
                )
            )
        return result


def _root_of(by_id: dict, category_id: UUID) -> UUID:
    """Top-level ancestor of a category (itself when it has no parent)."""
    seen: set[UUID] = set()
    current = category_id
    while current in by_id and by_id[current].parent_id is not None and current not in seen:
        seen.add(current)
        current = by_id[current].parent_id
    return current


class GetTrend(_AnalyticsUseCase):
    """Income and expense per day, month or year, every bucket present, ascending."""

    def __init__(
        self,
        transactions: TransactionRepository,
        profiles: ProfileRepository,
        rates: ExchangeRateRepository,
        clock: Clock,
    ) -> None:
        super().__init__(transactions, profiles, rates)
        self._clock = clock

    def execute(
        self,
        user_id: UUID,
        granularity: Granularity,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[TrendPointDTO]:
        today = self._clock.now().date()
        date_to = date_to or today
        date_from = date_from or _default_trend_start(date_to, granularity)
        if date_from > date_to:
            msg = "date_from must not be after date_to."
            raise ValidationError(msg, field="date_from", field_code="invalid")
        step = _STEP[granularity]
        starts: list[date] = []
        current = _bucket_start(date_from, granularity)
        while current <= date_to:
            if len(starts) == MAX_TREND_POINTS:
                msg = f"A trend has at most {MAX_TREND_POINTS} points."
                raise ValidationError(msg, field="date_from", field_code="too_large")
            starts.append(current)
            current = current + step
        fx = self._converter(user_id)
        totals = self._transactions.period_totals(
            user_id, granularity=granularity, date_from=date_from, date_to=date_to
        )
        return [
            TrendPointDTO(
                start=start,
                income=fx.total(totals.get((start, TransactionType.INCOME))),
                expense=fx.total(totals.get((start, TransactionType.EXPENSE))),
            )
            for start in starts
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
