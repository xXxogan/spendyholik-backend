"""Use cases for the notifications bounded context."""

from __future__ import annotations

from uuid import UUID

from notifications.application.dto import NotificationDTO
from notifications.application.ports import NotificationRepository


def _dto(n) -> NotificationDTO:
    return NotificationDTO(id=n.id, type=n.type, title=n.title, body=n.body, is_read=n.is_read)


class ListNotifications:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    def execute(self, user_id: UUID) -> list[NotificationDTO]:
        return [_dto(n) for n in self._notifications.list_for_user(user_id)]


class MarkNotificationsRead:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    def execute(self, user_id: UUID, notification_id: UUID | None = None) -> None:
        if notification_id is None:
            self._notifications.mark_all_read(user_id)
        else:
            self._notifications.mark_read(user_id, notification_id)
