"""DRF views for analytics and dashboard."""

from datetime import date

from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

from core.interfaces import schemas as sc
from core.interfaces.api import BaseAPIView, ok, query_int
from core.interfaces.deps import container
from core.interfaces.permissions import IsVerified
from core.interfaces.renderers import category_ref_to_view, dashboard_to_view, money_to_view
from core.interfaces.schemas import api_doc, many
from finances.domain.enums import Granularity


def _parse_date(name: str, value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({name: "invalid"}) from exc


def _dates(request: Request):
    qp = request.query_params
    return _parse_date("date_from", qp.get("date_from")), _parse_date("date_to", qp.get("date_to"))


class DashboardView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.DashboardOut)
    def get(self, request: Request):
        return ok(dashboard_to_view(container.get_dashboard().execute(request.user.id)))


class SummaryView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.SummaryOut, parameters=sc.DATE_RANGE, errors=(401, 422))
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
    permission_classes = [IsVerified]

    @api_doc(
        many(sc.CategorySpendingOut),
        parameters=sc.DATE_RANGE,
        errors=(401, 422),
        description="Expenses per top-level category, largest first.",
    )
    def get(self, request: Request):
        date_from, date_to = _dates(request)
        rows = container.get_spending_by_category().execute(request.user.id, date_from, date_to)
        return ok(
            [
                {
                    "category": category_ref_to_view(r.category),
                    "category_id": str(r.category_id),
                    "category_name": r.category_name,
                    "amount": money_to_view(r.amount),
                    "ratio": r.ratio,
                }
                for r in rows
            ]
        )


class MonthlyTrendView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(many(sc.MonthlyPointOut), parameters=sc.MONTHS, errors=(401, 422))
    def get(self, request: Request):
        months = query_int(request, "months", 6)
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


class TrendView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(many(sc.TrendPointOut), parameters=sc.TREND, errors=(401, 422))
    def get(self, request: Request):
        raw = request.query_params.get("granularity") or Granularity.MONTH.value
        try:
            granularity = Granularity(raw)
        except ValueError as exc:
            raise ValidationError({"granularity": "invalid_choice"}) from exc
        date_from, date_to = _dates(request)
        rows = container.get_trend().execute(request.user.id, granularity, date_from, date_to)
        return ok(
            [
                {
                    "start": r.start.isoformat(),
                    "income": money_to_view(r.income),
                    "expense": money_to_view(r.expense),
                }
                for r in rows
            ]
        )
