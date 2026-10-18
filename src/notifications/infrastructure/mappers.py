"""ORM ↔ domain mappers for the notifications bounded context."""

from notifications.domain.entities import Notification
from notifications.domain.enums import NotificationType
from notifications.infrastructure.orm.models import Notification as NotificationORM


def notification_to_domain(orm: NotificationORM) -> Notification:
    return Notification(
        id=orm.id,
        user_id=orm.user_id,
        type=NotificationType(orm.type),
        title=orm.title,
        body=orm.body,
        is_read=orm.is_read,
    )


def notification_to_orm(n: Notification) -> NotificationORM:
    return NotificationORM(
        id=n.id,
        user_id=n.user_id,
        type=n.type.value,
        title=n.title,
        body=n.body,
        is_read=n.is_read,
    )
