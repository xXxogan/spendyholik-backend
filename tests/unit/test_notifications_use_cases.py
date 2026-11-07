from uuid import uuid4

import pytest

from notifications.application.use_cases import ListNotifications, MarkNotificationsRead
from notifications.domain.entities import Notification
from notifications.domain.enums import NotificationType
from notifications.domain.exceptions import NotificationNotFoundError
from tests.fakes import InMemoryNotificationRepository

USER = uuid4()


def _repo():
    repo = InMemoryNotificationRepository()
    repo.add(
        Notification(
            user_id=USER, type=NotificationType.INCOME_RECEIVED, subject="ООО", amount_minor=100
        )
    )
    return repo


class TestNotifications:
    def test_list(self):
        result = ListNotifications(_repo()).execute(USER)
        assert len(result) == 1
        assert result[0].is_read is False

    def test_mark_all_read(self):
        repo = _repo()
        MarkNotificationsRead(repo).execute(USER)
        assert all(n.is_read for n in ListNotifications(repo).execute(USER))
        assert repo.unread_count(USER) == 0

    def test_mark_one_read(self):
        repo = _repo()
        [item] = ListNotifications(repo).execute(USER)
        MarkNotificationsRead(repo).execute(USER, item.id)
        assert repo.unread_count(USER) == 0

    def test_mark_unknown_read_raises(self):
        with pytest.raises(NotificationNotFoundError):
            MarkNotificationsRead(_repo()).execute(USER, uuid4())
