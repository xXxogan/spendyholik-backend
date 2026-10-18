"""DRF views for analytics and dashboard."""

from datetime import date

from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, ok
from core.interfaces.deps import container
from core.interfaces.renderers import dashboard_to_view, money_to_view


def _parse_date(name: str, value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({name: "Expected an ISO date (YYYY-MM-DD)."}) from exc


def _dates(request: Request):
    qp = request.query_params
    return _parse_date("date_from", qp.get("date_from")), _parse_date("date_to", qp.get("date_to"))


class DashboardView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok(dashboard_to_view(container.get_dashboard().execute(request.user.id)))


class SummaryView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        date_from, date_to = _dates(request)
        summary = container.get_summary().execute(request.user.id, date_from, date_to)
        return ok(
            {
                "income": money_to_view(summary.income),
                "expense": money_to_view(summary.expense),
                "net": money_to_view(summary.net),
                "excluded_currencies": summary.excluded_currencies,
            }
        )


class SpendingByCategoryView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        date_from, date_to = _dates(request)
        rows = container.get_spending_by_category().execute(request.user.id, date_from, date_to)
        return ok(
            [
                {
                    "category_id": str(r.category_id),
                    "category_name": r.category_name,
                    "amount": money_to_view(r.amount),
                    "ratio": r.ratio,
                }
                for r in rows
            ]
        )


class MonthlyTrendView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        try:
            months = int(request.query_params.get("months", 6))
        except ValueError as exc:
            raise ValidationError({"months": "Expected an integer."}) from exc
        rows = container.get_monthly_trend().execute(request.user.id, months)
        return ok(
            [
                {
                    "month": r.month.isoformat(),
                    "income": money_to_view(r.income),
                    "expense": money_to_view(r.expense),
                }
                for r in rows
            ]
        )
