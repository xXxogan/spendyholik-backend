"""URL routes for the goals module (relative to /api/v1/)."""

from django.urls import path

from goals.interfaces.views import (
    GoalContributeView,
    GoalContributionListView,
    GoalDetailView,
    GoalForecastView,
    GoalListCreateView,
)

app_name = "goals"

urlpatterns = [
    path("goals/", GoalListCreateView.as_view(), name="goal-list"),
    path("goals/<uuid:pk>/", GoalDetailView.as_view(), name="goal-detail"),
    path("goals/<uuid:pk>/contribute/", GoalContributeView.as_view(), name="goal-contribute"),
    path(
        "goals/<uuid:pk>/contributions/",
        GoalContributionListView.as_view(),
        name="goal-contributions",
    ),
    path("goals/<uuid:pk>/forecast/", GoalForecastView.as_view(), name="goal-forecast"),
]
