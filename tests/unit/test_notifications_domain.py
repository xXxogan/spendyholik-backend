from uuid import uuid4

from notifications.domain.entities import Notification
from notifications.domain.enums import NotificationType


class TestNotification:
    def test_creates(self):
        n = Notification(user_id=uuid4(), type=NotificationType.BUDGET_THRESHOLD, title="Бюджет")
        assert n.is_read is False
        assert n.body == ""

    def test_type_values(self):
        assert {t.value for t in NotificationType} == {
            "system", "budget_threshold", "goal_progress", "upcoming_recurring", "weekly_report",
        }
