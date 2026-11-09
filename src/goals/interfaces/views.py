"""DRF views for the goals bounded context."""

from __future__ import annotations

from uuid import UUID

from rest_framework.request import Request

from core.interfaces import schemas as sc
from core.interfaces.api import BaseAPIView, created, no_content, ok
from core.interfaces.deps import container
from core.interfaces.permissions import IsVerified
from core.interfaces.renderers import contribution_to_view, goal_to_view, money_to_view
from core.interfaces.schemas import api_doc, many
from goals.application.dto import ContributeToGoalInput, CreateGoalInput, UpdateGoalInput


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


class GoalListCreateView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(many(sc.GoalOut), operation_id="api_v1_goals_list")
    def get(self, request: Request):
        return ok([goal_to_view(g) for g in container.list_goals().execute(request.user.id)])

    @api_doc(sc.GoalOut, request=CreateGoalInput, status=201, errors=sc.WRITE)
    def post(self, request: Request):
        data = self.parse(CreateGoalInput, request.data)
        return created(goal_to_view(container.create_goal().execute(request.user.id, data)))


class GoalDetailView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.GoalOut, errors=sc.READ)
    def get(self, request: Request, pk):
        return ok(goal_to_view(container.get_goal_detail().execute(request.user.id, _uuid(pk))))

    @api_doc(sc.GoalOut, request=UpdateGoalInput, errors=sc.WRITE)
    def patch(self, request: Request, pk):
        data = self.parse(UpdateGoalInput, request.data)
        return ok(goal_to_view(container.update_goal().execute(request.user.id, _uuid(pk), data)))

    @api_doc(
        None, status=204, errors=sc.READ, description="Contributions go back to their accounts."
    )
    def delete(self, request: Request, pk):
        container.delete_goal().execute(request.user.id, _uuid(pk))
        return no_content()


class GoalContributeView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.ContributionOut, request=ContributeToGoalInput, status=201, errors=sc.WRITE)
    def post(self, request: Request, pk):
        data = self.parse(ContributeToGoalInput, request.data)
        contribution = container.contribute_to_goal().execute(request.user.id, _uuid(pk), data)
        return created(contribution_to_view(contribution))


class GoalContributionListView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(many(sc.ContributionOut), errors=sc.READ, description="Newest first.")
    def get(self, request: Request, pk):
        items = container.list_goal_contributions().execute(request.user.id, _uuid(pk))
        return ok([contribution_to_view(c) for c in items])


class GoalForecastView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.ForecastOut, errors=sc.READ)
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
