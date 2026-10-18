"""Django ORM implementations of the notifications ports."""

from uuid import UUID

from notifications.application.ports import NotificationRepository
from notifications.domain.entities import Notification
from notifications.infrastructure.mappers import notification_to_domain, notification_to_orm
from notifications.infrastructure.orm.models import Notification as NotificationORM


class DjangoNotificationRepository(NotificationRepository):
    def add(self, notification: Notification) -> Notification:
        notification_to_orm(notification).save(force_insert=True)
        return notification

    def list_for_user(self, user_id: UUID) -> list[Notification]:
        return [notification_to_domain(n) for n in NotificationORM.objects.filter(user_id=user_id)]

    def unread_count(self, user_id: UUID) -> int:
        return NotificationORM.objects.filter(user_id=user_id, is_read=False).count()

    def mark_read(self, user_id: UUID, notification_id: UUID) -> None:
        NotificationORM.objects.filter(pk=notification_id, user_id=user_id).update(is_read=True)

    def mark_all_read(self, user_id: UUID) -> None:
        NotificationORM.objects.filter(user_id=user_id, is_read=False).update(is_read=True)
