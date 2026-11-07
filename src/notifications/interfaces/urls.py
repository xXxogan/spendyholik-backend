"""URL routes for notifications (relative to /api/v1/)."""

from django.urls import path

from notifications.interfaces.views import (
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
)

app_name = "notifications"

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path(
        "notifications/read-all/", NotificationReadAllView.as_view(), name="notification-read-all"
    ),
    path("notifications/<uuid:pk>/read/", NotificationReadView.as_view(), name="notification-read"),
]
