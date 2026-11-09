"""DRF views for the notifications bounded context."""

from uuid import UUID

from rest_framework.request import Request

from core.interfaces import schemas as sc
from core.interfaces.api import BaseAPIView, ok
from core.interfaces.deps import container
from core.interfaces.permissions import IsVerified
from core.interfaces.renderers import notification_to_view
from core.interfaces.schemas import api_doc, many


class NotificationListView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(many(sc.NotificationOut), description="Newest first.")
    def get(self, request: Request):
        return ok(
            [
                notification_to_view(n)
                for n in container.list_notifications().execute(request.user.id)
            ]
        )


class NotificationReadAllView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.DetailOut, request=None)
    def post(self, request: Request):
        container.mark_notifications_read().execute(request.user.id)
        return ok({"detail": "ok"})


class NotificationReadView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(sc.DetailOut, request=None, errors=sc.READ)
    def post(self, request: Request, pk: UUID):
        container.mark_notifications_read().execute(request.user.id, pk)
        return ok({"detail": "ok"})
