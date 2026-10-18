"""DRF views for the goals bounded context."""

from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, created, no_content, ok
from core.interfaces.deps import container
from core.interfaces.renderers import goal_to_view, money_to_view
from goals.application.dto import ContributeToGoalInput, CreateGoalInput, UpdateGoalInput


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


class GoalListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([goal_to_view(g) for g in container.list_goals().execute(request.user.id)])

    def post(self, request: Request):
        data = self.parse(CreateGoalInput, request.data)
        return created(goal_to_view(container.create_goal().execute(request.user.id, data)))


class GoalDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk):
        return ok(goal_to_view(container.get_goal_detail().execute(request.user.id, _uuid(pk))))

    def patch(self, request: Request, pk):
        data = self.parse(UpdateGoalInput, request.data)
        return ok(goal_to_view(container.update_goal().execute(request.user.id, _uuid(pk), data)))

    def delete(self, request: Request, pk):
        container.delete_goal().execute(request.user.id, _uuid(pk))
        return no_content()


class GoalContributeView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk):
        data = self.parse(ContributeToGoalInput, request.data)
        contribution = container.contribute_to_goal().execute(request.user.id, _uuid(pk), data)
        return created(
            {
                "id": str(contribution.id),
                "goal_id": str(contribution.goal_id),
                "account_id": str(contribution.account_id),
                "amount": money_to_view(contribution.amount),
                "date": contribution.date.isoformat(),
            }
        )


class GoalForecastView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk):
        forecast = container.forecast_goal().execute(request.user.id, _uuid(pk))
        return ok(
            {
                "goal_id": str(forecast.goal_id),
                "remaining": money_to_view(forecast.remaining),
                "projected_completion": (
                    forecast.projected_completion.isoformat()
                    if forecast.projected_completion
                    else None
                ),
            }
        )
