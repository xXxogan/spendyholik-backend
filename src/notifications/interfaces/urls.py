"""URL routes for notifications (relative to /api/v1/)."""

from django.urls import path

from notifications.interfaces.views import NotificationListView, NotificationReadAllView

app_name = "notifications"

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/read-all/", NotificationReadAllView.as_view(), name="notification-read-all"),
]
