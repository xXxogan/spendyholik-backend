"""DRF views for the notifications bounded context."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, ok
from core.interfaces.deps import container
from core.interfaces.renderers import notification_to_view


class NotificationListView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([notification_to_view(n) for n in container.list_notifications().execute(request.user.id)])


class NotificationReadAllView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        container.mark_notifications_read().execute(request.user.id)
        return ok({"detail": "ok"})
