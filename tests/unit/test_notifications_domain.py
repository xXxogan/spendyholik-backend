from uuid import uuid4

from notifications.domain.entities import Notification
from notifications.domain.enums import NotificationType


class TestNotification:
    def test_creates(self):
        n = Notification(
            user_id=uuid4(),
            type=NotificationType.BUDGET_ALMOST_SPENT,
            subject="Еда",
            percent=90,
        )
        assert n.is_read is False
        assert n.title == ""
        assert n.amount_minor is None

    def test_type_values(self):
        assert {t.value for t in NotificationType} == {
            "budget_almost_spent",
            "income_received",
            "recurring_tomorrow",
            "goal_progress",
        }
