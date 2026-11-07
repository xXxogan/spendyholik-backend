"""API smoke tests for goals, debts, recurring, analytics, notifications, health."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestGoals:
    def test_create_and_contribute(self, auth_client):
        acct = auth_client.post(
            "/api/v1/accounts/",
            {
                "name": "Счёт",
                "type": "debit",
                "currency": "RUB",
                "initial_balance_minor": 30000_00,
            },
            format="json",
        ).json()
        goal = auth_client.post(
            "/api/v1/goals/",
            {
                "name": "Подушка",
                "target_amount_minor": 100000_00,
                "currency": "RUB",
                "account_id": acct["id"],
            },
            format="json",
        )
        assert goal.status_code == 201
        gid = goal.json()["id"]
        resp = auth_client.post(
            f"/api/v1/goals/{gid}/contribute/",
            {"account_id": acct["id"], "amount_minor": 25000_00, "date": "2026-03-15"},
            format="json",
        )
        assert resp.status_code == 201
        detail = auth_client.get(f"/api/v1/goals/{gid}/").json()
        assert detail["current_amount"]["minor"] == 25000_00
        assert detail["progress"] == 0.25


@pytest.mark.django_db
class TestDebts:
    def test_create_and_repay(self, auth_client):
        acct = auth_client.post(
            "/api/v1/accounts/",
            {"name": "Счёт", "type": "debit", "currency": "RUB", "initial_balance_minor": 1000_00},
            format="json",
        ).json()
        debt = auth_client.post(
            "/api/v1/debts/",
            {
                "person_name": "Иван",
                "direction": "i_owe",
                "amount_minor": 1000_00,
                "currency": "RUB",
            },
            format="json",
        ).json()
        resp = auth_client.post(
            f"/api/v1/debts/{debt['id']}/repay/",
            {"account_id": acct["id"], "amount_minor": 1000_00, "date": "2026-03-15"},
            format="json",
        )
        assert resp.status_code == 201
        detail = auth_client.get(f"/api/v1/debts/{debt['id']}/").json()
        assert detail["is_closed"] is True
        assert detail["remaining"]["minor"] == 0


@pytest.mark.django_db
class TestRecurring:
    def test_create_and_toggle(self, auth_client):
        acct = auth_client.post(
            "/api/v1/accounts/", {"name": "Счёт", "type": "debit", "currency": "RUB"}, format="json"
        ).json()
        r = auth_client.post(
            "/api/v1/recurring/",
            {
                "name": "Аренда",
                "amount_minor": 40000_00,
                "type": "expense",
                "account_id": acct["id"],
                "frequency": "monthly",
                "next_run": "2026-04-01",
            },
            format="json",
        ).json()
        resp = auth_client.post(
            f"/api/v1/recurring/{r['id']}/toggle/", {"is_active": False}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


@pytest.mark.django_db
class TestAnalytics:
    def test_dashboard_and_summary(self, auth_client):
        from datetime import date

        today = date.today().isoformat()
        acct = auth_client.post(
            "/api/v1/accounts/",
            {
                "name": "Счёт",
                "type": "debit",
                "currency": "RUB",
                "initial_balance_minor": 100000_00,
            },
            format="json",
        ).json()
        cat = auth_client.post(
            "/api/v1/categories/", {"name": "Еда", "type": "expense"}, format="json"
        ).json()
        auth_client.post(
            "/api/v1/transactions/",
            {
                "account_id": acct["id"],
                "category_id": cat["id"],
                "type": "expense",
                "amount_minor": 20000_00,
                "date": today,
            },
            format="json",
        )
        dash = auth_client.get("/api/v1/dashboard/")
        assert dash.status_code == 200
        assert dash.json()["expense_this_month"]["minor"] == 20000_00

        summary = auth_client.get("/api/v1/analytics/summary/")
        assert summary.status_code == 200
        assert summary.json()["expense"]["minor"] == 20000_00


@pytest.mark.django_db
class TestHealth:
    def test_health_ready(self, api_client):
        assert api_client.get("/health/").status_code == 200
        assert api_client.get("/ready/").status_code == 200
