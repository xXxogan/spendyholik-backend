from uuid import uuid4

from notifications.application.use_cases import ListNotifications, MarkNotificationsRead
from notifications.domain.entities import Notification
from notifications.domain.enums import NotificationType
from tests.fakes import InMemoryNotificationRepository

USER = uuid4()


def _repo():
    repo = InMemoryNotificationRepository()
    repo.add(Notification(user_id=USER, type=NotificationType.SYSTEM, title="Hello", body="World"))
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
