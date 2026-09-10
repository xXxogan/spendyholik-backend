"""URL routes for the debts module (relative to /api/v1/)."""

from django.urls import path

from debts.interfaces.views import DebtDetailView, DebtListCreateView, DebtRepayView

app_name = "debts"

urlpatterns = [
    path("debts/", DebtListCreateView.as_view(), name="debt-list"),
    path("debts/<uuid:pk>/", DebtDetailView.as_view(), name="debt-detail"),
    path("debts/<uuid:pk>/repay/", DebtRepayView.as_view(), name="debt-repay"),
]
