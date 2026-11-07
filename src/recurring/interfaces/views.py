"""DRF views for the recurring bounded context."""

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces import schemas as sc
from core.interfaces.api import BaseAPIView, created, no_content, ok
from core.interfaces.deps import container
from core.interfaces.renderers import recurring_to_view
from core.interfaces.schemas import api_doc, many
from recurring.application.dto import (
    CreateRecurringInput,
    ToggleRecurringInput,
    UpdateRecurringInput,
)


def _uuid(value):
    return value if isinstance(value, UUID) else UUID(value)


class RecurringListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(many(sc.RecurringOut))
    def get(self, request: Request):
        return ok(
            [recurring_to_view(r) for r in container.list_recurring().execute(request.user.id)]
        )

    @api_doc(sc.RecurringOut, request=CreateRecurringInput, status=201, errors=sc.WRITE)
    def post(self, request: Request):
        data = self.parse(CreateRecurringInput, request.data)
        return created(
            recurring_to_view(container.create_recurring().execute(request.user.id, data))
        )


class RecurringDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.RecurringOut, request=UpdateRecurringInput, errors=sc.WRITE)
    def patch(self, request: Request, pk):
        data = self.parse(UpdateRecurringInput, request.data)
        return ok(
            recurring_to_view(
                container.update_recurring().execute(request.user.id, _uuid(pk), data)
            )
        )

    @api_doc(None, status=204, errors=sc.READ)
    def delete(self, request: Request, pk):
        container.delete_recurring().execute(request.user.id, _uuid(pk))
        return no_content()


class RecurringToggleView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.RecurringOut, request=ToggleRecurringInput, errors=sc.WRITE)
    def post(self, request: Request, pk):
        # Parsed, not bool()-cast: the string "false" must mean False.
        data = self.parse(ToggleRecurringInput, request.data)
        return ok(
            recurring_to_view(
                container.toggle_recurring().execute(request.user.id, _uuid(pk), data.is_active)
            )
        )
