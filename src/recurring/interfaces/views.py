"""DRF views for the recurring bounded context."""

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, created, no_content, ok
from core.interfaces.deps import container
from core.interfaces.renderers import recurring_to_view
from recurring.application.dto import (
    CreateRecurringInput,
    ToggleRecurringInput,
    UpdateRecurringInput,
)


def _uuid(value):
    return value if isinstance(value, UUID) else UUID(value)


class RecurringListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok(
            [recurring_to_view(r) for r in container.list_recurring().execute(request.user.id)]
        )

    def post(self, request: Request):
        data = self.parse(CreateRecurringInput, request.data)
        return created(
            recurring_to_view(container.create_recurring().execute(request.user.id, data))
        )


class RecurringDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, pk):
        data = self.parse(UpdateRecurringInput, request.data)
        return ok(
            recurring_to_view(
                container.update_recurring().execute(request.user.id, _uuid(pk), data)
            )
        )

    def delete(self, request: Request, pk):
        container.delete_recurring().execute(request.user.id, _uuid(pk))
        return no_content()


class RecurringToggleView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk):
        # Parsed, not bool()-cast: the string "false" must mean False.
        data = self.parse(ToggleRecurringInput, request.data)
        return ok(
            recurring_to_view(
                container.toggle_recurring().execute(request.user.id, _uuid(pk), data.is_active)
            )
        )
