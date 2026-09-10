"""DRF views for the recurring bounded context."""

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, created, ok
from core.interfaces.deps import container
from core.interfaces.renderers import recurring_to_view
from recurring.application.dto import CreateRecurringInput, UpdateRecurringInput


def _uuid(value):
    return value if isinstance(value, UUID) else UUID(value)


class RecurringListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([recurring_to_view(r) for r in container.list_recurring().execute(request.user.id)])

    def post(self, request: Request):
        data = self.parse(CreateRecurringInput, request.data)
        return created(recurring_to_view(container.create_recurring().execute(request.user.id, data)))


class RecurringDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, pk):
        data = self.parse(UpdateRecurringInput, request.data)
        return ok(recurring_to_view(container.update_recurring().execute(request.user.id, _uuid(pk), data)))

    def delete(self, request: Request, pk):
        from recurring.infrastructure.repositories import DjangoRecurringTransactionRepository

        DjangoRecurringTransactionRepository().delete(_uuid(pk), request.user.id)
        return ok({"detail": "ok"})


class RecurringToggleView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk):
        is_active = bool(request.data.get("is_active", True))
        return ok(recurring_to_view(container.toggle_recurring().execute(request.user.id, _uuid(pk), is_active)))
