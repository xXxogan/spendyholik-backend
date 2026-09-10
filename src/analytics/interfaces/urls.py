"""URL routes for analytics (relative to /api/v1/)."""

from django.urls import path

from analytics.interfaces.views import (
    DashboardView,
    MonthlyTrendView,
    SpendingByCategoryView,
    SummaryView,
)

app_name = "analytics"

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("analytics/summary/", SummaryView.as_view(), name="summary"),
    path("analytics/by-category/", SpendingByCategoryView.as_view(), name="by-category"),
    path("analytics/monthly/", MonthlyTrendView.as_view(), name="monthly"),
]
