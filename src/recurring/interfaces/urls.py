"""URL routes for the recurring module (relative to /api/v1/)."""

from django.urls import path

from recurring.interfaces.views import (
    RecurringDetailView,
    RecurringListCreateView,
    RecurringToggleView,
)

app_name = "recurring"

urlpatterns = [
    path("recurring/", RecurringListCreateView.as_view(), name="recurring-list"),
    path("recurring/<uuid:pk>/", RecurringDetailView.as_view(), name="recurring-detail"),
    path("recurring/<uuid:pk>/toggle/", RecurringToggleView.as_view(), name="recurring-toggle"),
]
