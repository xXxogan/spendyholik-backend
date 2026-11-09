"""B-19: the server creates notifications."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from accounts.infrastructure.orm.models import Profile
from notifications.infrastructure.orm.models import Notification

pytestmark = pytest.mark.django_db

TODAY = date.today()


def _account(client, initial=100000_00):
    return client.post(
        "/api/v1/accounts/",
        {"name": "Карта", "type": "debit", "currency": "RUB", "initial_balance_minor": initial},
        format="json",
    ).json()


def _category(client, name, type_="expense", parent_id=None):
    return client.post(
        "/api/v1/categories/",
        {"name": name, "type": type_, "parent_id": parent_id},
        format="json",
    ).json()


def _tx(client, account_id, amount, category_id, type_="expense", **extra):
    return client.post(
        "/api/v1/transactions/",
        {
            "account_id": account_id,
            "type": type_,
            "amount_minor": amount,
            "date": TODAY.isoformat(),
            "category_id": category_id,
        }
        | extra,
        format="json",
    ).json()


def _feed(client):
    return client.get("/api/v1/notifications/").json()


class TestBudget:
    def test_once_per_period_when_80_percent_is_reached(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client, "Еда")
        cafe = _category(auth_client, "Кафе", parent_id=food["id"])
        auth_client.post(
            "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 1000_00}, format="json"
        )
        _tx(auth_client, card["id"], 700_00, food["id"])
        assert _feed(auth_client) == []
        _tx(auth_client, card["id"], 150_00, cafe["id"])  # subcategory → 85 %
        [n] = _feed(auth_client)
        assert (n["type"], n["subject"], n["percent"], n["amount_minor"], n["currency"]) == (
            "budget_almost_spent",
            "Еда",
            85,
            850_00,
            "RUB",
        )
        _tx(auth_client, card["id"], 100_00, food["id"])
        assert len(_feed(auth_client)) == 1

    def test_editing_an_expense_up_triggers_it(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client, "Еда")
        auth_client.post(
            "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 1000_00}, format="json"
        )
        tx = _tx(auth_client, card["id"], 100_00, food["id"])
        auth_client.patch(
            f"/api/v1/transactions/{tx['id']}/", {"amount_minor": 900_00}, format="json"
        )
        assert [n["percent"] for n in _feed(auth_client)] == [90]

    def test_muted_by_the_profile(self, auth_client, user):
        Profile.objects.filter(user=user).update(notify_budget=False)
        card = _account(auth_client)
        food = _category(auth_client, "Еда")
        auth_client.post(
            "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 100_00}, format="json"
        )
        _tx(auth_client, card["id"], 100_00, food["id"])
        assert _feed(auth_client) == []


class TestIncome:
    def test_new_income(self, auth_client):
        card = _account(auth_client)
        salary = _category(auth_client, "Зарплата", type_="income")
        _tx(auth_client, card["id"], 50000_00, salary["id"], type_="income")
        _tx(auth_client, card["id"], 100_00, salary["id"], type_="income", title="Кешбэк")
        assert [(n["subject"], n["amount_minor"]) for n in _feed(auth_client)] == [
            ("Кешбэк", 100_00),
            ("Зарплата", 50000_00),
        ]
        assert {n["type"] for n in _feed(auth_client)} == {"income_received"}

    def test_muted(self, auth_client, user):
        Profile.objects.filter(user=user).update(notify_income=False)
        card = _account(auth_client)
        salary = _category(auth_client, "Зарплата", type_="income")
        _tx(auth_client, card["id"], 100_00, salary["id"], type_="income")
        assert _feed(auth_client) == []


class TestGoal:
    def test_thresholds_once_each_highest_crossed(self, auth_client):
        card = _account(auth_client)
        goal = auth_client.post(
            "/api/v1/goals/",
            {"name": "Отпуск", "target_amount_minor": 1000_00, "currency": "RUB"},
            format="json",
        ).json()

        def contribute(amount):
            auth_client.post(
                f"/api/v1/goals/{goal['id']}/contribute/",
                {"account_id": card["id"], "amount_minor": amount, "date": TODAY.isoformat()},
                format="json",
            )

        contribute(400_00)  # 40 %
        assert _feed(auth_client) == []
        contribute(400_00)  # 80 % → 75
        contribute(100_00)  # 90 %
        contribute(100_00)  # 100 %
        assert [(n["percent"], n["subject"]) for n in _feed(auth_client)] == [
            (100, "Отпуск"),
            (75, "Отпуск"),
        ]


class TestRecurringReminder:
    def test_reminds_about_tomorrow_once(self, auth_client):
        card = _account(auth_client)
        rent = _category(auth_client, "Аренда")
        tomorrow = (TODAY + timedelta(days=1)).isoformat()
        for name, run in (("Аренда", tomorrow), ("Спорт", (TODAY + timedelta(days=3)).isoformat())):
            auth_client.post(
                "/api/v1/recurring/",
                {
                    "name": name,
                    "amount_minor": 40000_00,
                    "type": "expense",
                    "account_id": card["id"],
                    "category_id": rent["id"],
                    "frequency": "monthly",
                    "next_run": run,
                },
                format="json",
            )
        from tasks.tasks import notify_upcoming_recurring

        assert notify_upcoming_recurring() == {"notified": 1}
        assert notify_upcoming_recurring() == {"notified": 0}
        [n] = _feed(auth_client)
        assert (n["type"], n["subject"], n["amount_minor"]) == (
            "recurring_tomorrow",
            "Аренда",
            40000_00,
        )


def test_a_failing_notification_never_breaks_the_write(auth_client, monkeypatch):
    from notifications.application import triggers

    def boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(triggers.Notifier, "notify", boom)
    card = _account(auth_client)
    salary = _category(auth_client, "Зарплата", type_="income")
    resp = auth_client.post(
        "/api/v1/transactions/",
        {
            "account_id": card["id"],
            "type": "income",
            "amount_minor": 1_00,
            "date": TODAY.isoformat(),
            "category_id": salary["id"],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert not Notification.objects.exists()


class TestBudgetEdges:
    def _budget(self, client, amount=1000_00):
        card = _account(client)
        food = _category(client, "Еда")
        client.post(
            "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": amount}, format="json"
        )
        return card, food

    def test_huge_overspend_is_capped_not_lost(self, auth_client):
        card, food = self._budget(auth_client, amount=1)
        _tx(auth_client, card["id"], 5000_00, food["id"])
        [n] = _feed(auth_client)
        assert n["percent"] == 32767

    def test_expense_outside_the_period_does_not_notify(self, auth_client):
        card, food = self._budget(auth_client)
        _tx(auth_client, card["id"], 700_00, food["id"])
        last_year = (TODAY - timedelta(days=400)).isoformat()
        _tx(auth_client, card["id"], 200_00, food["id"], date=last_year)
        assert _feed(auth_client) == []

    def test_deleting_an_expense_does_not_notify(self, auth_client, user):
        card, food = self._budget(auth_client)
        Profile.objects.filter(user=user).update(notify_budget=False)
        tx = _tx(auth_client, card["id"], 900_00, food["id"])
        _tx(auth_client, card["id"], 10_00, food["id"])
        Profile.objects.filter(user=user).update(notify_budget=True)
        auth_client.delete(f"/api/v1/transactions/{tx['id']}/")
        assert _feed(auth_client) == []
