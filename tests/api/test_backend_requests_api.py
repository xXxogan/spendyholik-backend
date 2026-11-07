"""API contract for the client's phase-2 requests (R-01…R-101)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.test import override_settings

from notifications.infrastructure.orm.models import Notification

pytestmark = pytest.mark.django_db

TODAY = date.today()


def _post(client, path, data):
    return client.post(path, data, format="json")


def _patch(client, path, data):
    return client.patch(path, data, format="json")


def _account(client, initial=0, name="Карта", currency="RUB"):
    resp = _post(
        client,
        "/api/v1/accounts/",
        {"name": name, "type": "debit", "currency": currency, "initial_balance_minor": initial},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def _category(client, name="Еда", parent_id=None, type_="expense", color="cat-food"):
    resp = _post(
        client,
        "/api/v1/categories/",
        {"name": name, "type": type_, "parent_id": parent_id, "icon": "cart", "color": color},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def _tx(client, account_id, amount, type_="expense", on=TODAY, **extra):
    resp = _post(
        client,
        "/api/v1/transactions/",
        {
            "account_id": account_id,
            "type": type_,
            "amount_minor": amount,
            "date": on.isoformat(),
            **extra,
        },
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def _balance(client, account_id) -> int:
    return client.get(f"/api/v1/accounts/{account_id}/").json()["balance"]["minor"]


# ---------------------------------------------------------------------------
# R-01, R-02: error codes
# ---------------------------------------------------------------------------
class TestErrorCodes:
    def test_field_errors_are_codes(self, auth_client):
        resp = _post(auth_client, "/api/v1/transactions/", {"type": "nope", "account_id": "x"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_error"
        assert body["errors"] == {
            "account_id": "invalid",
            "type": "invalid_choice",
            "amount_minor": "required",
            "date": "required",
        }

    def test_empty_name_is_required_and_bounds_are_coded(self, auth_client):
        resp = _post(
            auth_client,
            "/api/v1/accounts/",
            {"name": "", "type": "debit", "currency": "RUB"},
        )
        assert resp.json()["errors"] == {"name": "required"}
        resp = _post(
            auth_client,
            "/api/v1/accounts/",
            {"name": "x" * 121, "type": "debit", "currency": "RUB"},
        )
        assert resp.json()["errors"] == {"name": "too_long"}
        acct = _account(auth_client)
        resp = _post(
            auth_client,
            "/api/v1/transactions/",
            {"account_id": acct["id"], "type": "expense", "amount_minor": 0, "date": "2026-01-01"},
        )
        assert resp.json()["errors"] == {"amount_minor": "too_small"}

    def test_null_for_required_patch_field(self, auth_client):
        acct = _account(auth_client)
        resp = _patch(auth_client, f"/api/v1/accounts/{acct['id']}/", {"name": None})
        assert resp.status_code == 422
        assert resp.json()["errors"] == {"name": "required"}

    def test_bad_query_parameter(self, auth_client):
        resp = auth_client.get("/api/v1/analytics/summary/?date_from=yesterday")
        assert resp.status_code == 422
        assert resp.json()["errors"] == {"date_from": "invalid"}

    def test_wrong_password_is_a_field_error_not_a_401(self, auth_client):
        resp = _patch(
            auth_client,
            "/api/v1/profile/password/",
            {"old_password": "nope-nope", "new_password": "newpassword1"},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "wrong_password"
        assert resp.json()["errors"] == {"old_password": "wrong_password"}


# ---------------------------------------------------------------------------
# R-04: CORS
# ---------------------------------------------------------------------------
@override_settings(CORS_ALLOWED_ORIGIN_REGEXES=[r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"])
def test_cors_allows_local_web_on_any_port(api_client):
    resp = api_client.options(
        "/api/v1/auth/login/",
        HTTP_ORIGIN="http://localhost:61234",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert resp.headers["access-control-allow-origin"] == "http://localhost:61234"
    other = api_client.options(
        "/api/v1/auth/login/",
        HTTP_ORIGIN="http://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert "access-control-allow-origin" not in other.headers


# ---------------------------------------------------------------------------
# R-10, R-11: profile
# ---------------------------------------------------------------------------
class TestProfile:
    def test_name_and_email(self, auth_client, user):
        body = auth_client.get("/api/v1/profile/").json()
        assert body["email"] == user.email
        resp = _patch(auth_client, "/api/v1/profile/", {"first_name": "Аня", "email": "an@ya.ru"})
        assert resp.status_code == 200
        assert (resp.json()["first_name"], resp.json()["email"]) == ("Аня", "an@ya.ru")
        user.refresh_from_db()
        assert user.email == "an@ya.ru"

    def test_taken_email(self, auth_client, api_client):
        _post(
            api_client,
            "/api/v1/auth/register/",
            {"email": "taken@ya.ru", "password": "password123"},
        )
        resp = _patch(auth_client, "/api/v1/profile/", {"email": "taken@ya.ru"})
        assert resp.status_code == 409
        assert resp.json()["errors"] == {"email": "email_already_taken"}

    def test_delete_all_data_keeps_the_user(self, auth_client):
        acct = _account(auth_client, 1000_00)
        food = _category(auth_client)
        _tx(auth_client, acct["id"], 100_00, category_id=food["id"])
        _post(auth_client, "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 1_00})
        _post(
            auth_client,
            "/api/v1/goals/",
            {"name": "Цель", "target_amount_minor": 100_00, "currency": "RUB"},
        )
        assert auth_client.delete("/api/v1/profile/data/").status_code == 204
        for path in ("accounts/?include_archived=true", "categories/", "budgets/", "goals/"):
            assert auth_client.get(f"/api/v1/{path}").json() == [], path
        assert auth_client.get("/api/v1/transactions/").json()["items"] == []
        assert auth_client.get("/api/v1/profile/").status_code == 200


# ---------------------------------------------------------------------------
# R-20…R-23: accounts
# ---------------------------------------------------------------------------
class TestAccounts:
    def test_balance_counts_every_movement(self, auth_client):
        card = _account(auth_client, 1000_00)
        cash = _account(auth_client, 0, name="Наличные")
        _tx(auth_client, card["id"], 100_00)
        _tx(auth_client, card["id"], 50_00, type_="income")
        _tx(auth_client, card["id"], 200_00, type_="transfer", transfer_to_account_id=cash["id"])
        goal = _post(
            auth_client,
            "/api/v1/goals/",
            {"name": "Цель", "target_amount_minor": 1000_00, "currency": "RUB"},
        ).json()
        _post(
            auth_client,
            f"/api/v1/goals/{goal['id']}/contribute/",
            {"account_id": card["id"], "amount_minor": 70_00, "date": TODAY.isoformat()},
        )
        assert _balance(auth_client, card["id"]) == 1000_00 - 100_00 + 50_00 - 200_00 - 70_00
        assert _balance(auth_client, cash["id"]) == 200_00
        listed = {
            a["id"]: a["balance"]["minor"] for a in auth_client.get("/api/v1/accounts/").json()
        }
        assert listed == {card["id"]: 680_00, cash["id"]: 200_00}
        dashboard = auth_client.get("/api/v1/dashboard/").json()
        assert dashboard["total_balance"]["minor"] == 880_00

    def test_patch_balance(self, auth_client):
        card = _account(auth_client, 1000_00)
        _tx(auth_client, card["id"], 300_00)
        resp = _patch(auth_client, f"/api/v1/accounts/{card['id']}/", {"balance_minor": 5000_00})
        assert resp.json()["balance"]["minor"] == 5000_00
        assert resp.json()["initial_balance"]["minor"] == 5300_00

    def test_unarchive(self, auth_client):
        card = _account(auth_client)
        _post(auth_client, f"/api/v1/accounts/{card['id']}/archive/", {})
        resp = _post(auth_client, f"/api/v1/accounts/{card['id']}/unarchive/", {})
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is False
        assert [a["id"] for a in auth_client.get("/api/v1/accounts/").json()] == [card["id"]]

    def test_balance_history(self, auth_client):
        card = _account(auth_client, 1000_00)
        _tx(auth_client, card["id"], 100_00, on=TODAY - timedelta(days=60))
        _tx(auth_client, card["id"], 40_00, on=TODAY - timedelta(days=3))
        resp = auth_client.get(f"/api/v1/accounts/{card['id']}/balance-history/?weeks=6")
        assert resp.status_code == 200
        points = [(p["at"], p["balance"]["minor"]) for p in resp.json()]
        assert points == [
            ((TODAY - timedelta(weeks=6)).isoformat(), 900_00),
            ((TODAY - timedelta(days=3)).isoformat(), 860_00),
            (TODAY.isoformat(), 860_00),
        ]

    def test_balance_history_validates_weeks(self, auth_client):
        card = _account(auth_client)
        resp = auth_client.get(f"/api/v1/accounts/{card['id']}/balance-history/?weeks=x")
        assert resp.json()["errors"] == {"weeks": "invalid"}


# ---------------------------------------------------------------------------
# R-30, R-31, R-40: transactions and categories
# ---------------------------------------------------------------------------
class TestTransactionsAndCategories:
    def test_account_refs_with_color(self, auth_client):
        card = _account(auth_client)
        cash = _account(auth_client, name="Наличные")
        tx = _tx(
            auth_client, card["id"], 10_00, type_="transfer", transfer_to_account_id=cash["id"]
        )
        assert tx["account"] == {"id": card["id"], "name": "Карта", "color": "default"}
        assert tx["transfer_to_account"] == {
            "id": cash["id"],
            "name": "Наличные",
            "color": "default",
        }
        expense = _tx(auth_client, card["id"], 10_00)
        assert expense["transfer_to_account"] is None

    def test_category_filter_includes_subcategories_and_counts(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client, "Еда")
        cafe = _category(auth_client, "Кафе", parent_id=food["id"])
        _tx(auth_client, card["id"], 10_00, category_id=food["id"])
        _tx(auth_client, card["id"], 20_00, category_id=cafe["id"])
        _tx(auth_client, card["id"], 20_00, category_id=cafe["id"])
        items = auth_client.get(f"/api/v1/transactions/?category_id={food['id']}").json()["items"]
        assert len(items) == 3
        counts = {
            c["name"]: c["transaction_count"] for c in auth_client.get("/api/v1/categories/").json()
        }
        assert counts == {"Еда": 1, "Кафе": 2}


# ---------------------------------------------------------------------------
# R-50, R-51: budgets
# ---------------------------------------------------------------------------
class TestBudgets:
    def test_budget_carries_category_spent_and_period(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client, "Еда")
        cafe = _category(auth_client, "Кафе", parent_id=food["id"])
        _tx(auth_client, card["id"], 100_00, category_id=food["id"])
        _tx(auth_client, card["id"], 50_00, category_id=cafe["id"])
        resp = _post(
            auth_client, "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 500_00}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["category"] == {
            "id": food["id"],
            "name": "Еда",
            "icon": "cart",
            "color": "cat-food",
        }
        assert body["spent"]["minor"] == 150_00
        assert body["period_start"] == TODAY.replace(day=1).isoformat()
        assert body["period_end"] >= TODAY.isoformat()

    def test_one_time_budget(self, auth_client):
        food = _category(auth_client)
        resp = _post(
            auth_client,
            "/api/v1/budgets/",
            {"category_id": food["id"], "amount_minor": 1_00, "period": "one_time"},
        )
        assert resp.status_code == 422
        assert resp.json()["errors"] == {"start_date": "required"}
        resp = _post(
            auth_client,
            "/api/v1/budgets/",
            {
                "category_id": food["id"],
                "amount_minor": 1_00,
                "period": "one_time",
                "start_date": "2026-05-01",
                "end_date": "2026-05-10",
            },
        )
        body = resp.json()
        assert (body["end_date"], body["period_start"], body["period_end"]) == (
            "2026-05-10",
            "2026-05-01",
            "2026-05-10",
        )
        updated = _patch(auth_client, f"/api/v1/budgets/{body['id']}/", {"end_date": "2026-05-20"})
        assert updated.json()["period_end"] == "2026-05-20"

    def test_one_budget_per_category(self, auth_client):
        food = _category(auth_client)
        _post(auth_client, "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 1_00})
        resp = _post(
            auth_client, "/api/v1/budgets/", {"category_id": food["id"], "amount_minor": 2_00}
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "budget_already_exists"
        assert resp.json()["errors"] == {"category_id": "budget_already_exists"}


# ---------------------------------------------------------------------------
# R-60…R-62: goals
# ---------------------------------------------------------------------------
class TestGoals:
    def test_goal_without_account_and_contribution_history(self, auth_client):
        card = _account(auth_client, 1000_00)
        goal = _post(
            auth_client,
            "/api/v1/goals/",
            {"name": "Отпуск", "target_amount_minor": 500_00, "currency": "RUB"},
        )
        assert goal.status_code == 201
        assert goal.json()["account_id"] is None
        gid = goal.json()["id"]
        for amount, on in ((100_00, "2026-03-01"), (50_00, "2026-03-05")):
            _post(
                auth_client,
                f"/api/v1/goals/{gid}/contribute/",
                {"account_id": card["id"], "amount_minor": amount, "date": on},
            )
        history = auth_client.get(f"/api/v1/goals/{gid}/contributions/").json()
        assert [(c["amount"]["minor"], c["date"]) for c in history] == [
            (50_00, "2026-03-05"),
            (100_00, "2026-03-01"),
        ]
        assert history[0]["account"] == {"id": card["id"], "name": "Карта", "color": "default"}

    def test_contribution_limits(self, auth_client):
        card = _account(auth_client, 100_00)
        gid = _post(
            auth_client,
            "/api/v1/goals/",
            {"name": "Отпуск", "target_amount_minor": 1000_00, "currency": "RUB"},
        ).json()["id"]
        resp = _post(
            auth_client,
            f"/api/v1/goals/{gid}/contribute/",
            {"account_id": card["id"], "amount_minor": 200_00, "date": "2026-03-01"},
        )
        assert resp.status_code == 409
        assert resp.json()["errors"] == {"amount_minor": "insufficient_funds"}
        resp = _post(
            auth_client,
            f"/api/v1/goals/{gid}/contribute/",
            {"account_id": card["id"], "amount_minor": 1001_00, "date": "2026-03-01"},
        )
        assert resp.json()["errors"] == {"amount_minor": "exceeds_target"}

    def test_initial_amount_needs_an_account(self, auth_client):
        resp = _post(
            auth_client,
            "/api/v1/goals/",
            {
                "name": "Отпуск",
                "target_amount_minor": 1000_00,
                "currency": "RUB",
                "initial_amount_minor": 10_00,
            },
        )
        assert resp.status_code == 422
        assert resp.json()["errors"] == {"account_id": "required"}

    def test_deleting_a_goal_returns_the_money(self, auth_client):
        card = _account(auth_client, 1000_00)
        goal = _post(
            auth_client,
            "/api/v1/goals/",
            {
                "name": "Отпуск",
                "target_amount_minor": 1000_00,
                "currency": "RUB",
                "account_id": card["id"],
                "initial_amount_minor": 300_00,
            },
        ).json()
        assert goal["current_amount"]["minor"] == 300_00
        assert _balance(auth_client, card["id"]) == 700_00
        assert auth_client.delete(f"/api/v1/goals/{goal['id']}/").status_code == 204
        assert _balance(auth_client, card["id"]) == 1000_00


# ---------------------------------------------------------------------------
# R-70…R-72: debts
# ---------------------------------------------------------------------------
class TestDebts:
    def _debt(self, client, direction="i_owe", amount=1000_00):
        resp = _post(
            client,
            "/api/v1/debts/",
            {
                "person_name": "Иван",
                "direction": direction,
                "amount_minor": amount,
                "currency": "RUB",
                "note": "до зарплаты",
            },
        )
        assert resp.status_code == 201, resp.json()
        return resp.json()

    def _repay(self, client, debt_id, account_id, amount):
        return _post(
            client,
            f"/api/v1/debts/{debt_id}/repay/",
            {"account_id": account_id, "amount_minor": amount, "date": TODAY.isoformat()},
        )

    def test_note_created_at_amount_edit_and_history(self, auth_client):
        card = _account(auth_client, 5000_00)
        debt = self._debt(auth_client)
        assert debt["note"] == "до зарплаты"
        assert debt["created_at"]
        assert self._repay(auth_client, debt["id"], card["id"], 400_00).status_code == 201
        resp = _patch(
            auth_client, f"/api/v1/debts/{debt['id']}/", {"amount_minor": 300_00, "note": ""}
        )
        assert resp.status_code == 409
        assert resp.json()["errors"] == {"amount_minor": "below_repaid"}
        resp = _patch(auth_client, f"/api/v1/debts/{debt['id']}/", {"amount_minor": 1500_00})
        assert resp.json()["remaining"]["minor"] == 1100_00
        history = auth_client.get(f"/api/v1/debts/{debt['id']}/history/").json()
        assert [(e["kind"], e["amount"]["minor"]) for e in history] == [
            ("repayment", 400_00),
            ("opened", 1500_00),
        ]
        assert history[0]["account"]["id"] == card["id"]
        assert history[1]["account"] is None

    def test_repayments_move_the_balance(self, auth_client):
        card = _account(auth_client, 1000_00)
        self._repay(auth_client, self._debt(auth_client, "i_owe")["id"], card["id"], 100_00)
        assert _balance(auth_client, card["id"]) == 900_00
        self._repay(auth_client, self._debt(auth_client, "owed_to_me")["id"], card["id"], 300_00)
        assert _balance(auth_client, card["id"]) == 1200_00

    def test_i_owe_repayment_needs_funds(self, auth_client):
        card = _account(auth_client, 10_00)
        resp = self._repay(auth_client, self._debt(auth_client)["id"], card["id"], 100_00)
        assert resp.status_code == 409
        assert resp.json()["errors"] == {"amount_minor": "insufficient_funds"}


# ---------------------------------------------------------------------------
# R-80, R-81: recurring
# ---------------------------------------------------------------------------
class TestRecurring:
    def test_refs_and_anchor(self, auth_client):
        card = _account(auth_client)
        rent = _category(auth_client, "Аренда")
        resp = _post(
            auth_client,
            "/api/v1/recurring/",
            {
                "name": "Аренда",
                "amount_minor": 40000_00,
                "type": "expense",
                "account_id": card["id"],
                "category_id": rent["id"],
                "frequency": "monthly",
                "anchor_date": "2026-01-31",
            },
        )
        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["anchor_date"] == "2026-01-31"
        assert body["next_run"] >= TODAY.isoformat()
        assert body["account"] == {"id": card["id"], "name": "Карта", "color": "default"}
        assert body["category"]["name"] == "Аренда"
        listed = auth_client.get("/api/v1/recurring/").json()
        assert listed[0]["category"]["icon"] == "cart"
        updated = _patch(
            auth_client,
            f"/api/v1/recurring/{body['id']}/",
            {"anchor_date": "2026-02-10", "next_run": "2026-12-10"},
        ).json()
        assert (updated["anchor_date"], updated["next_run"]) == ("2026-02-10", "2026-12-10")


# ---------------------------------------------------------------------------
# R-90, R-91: analytics
# ---------------------------------------------------------------------------
class TestAnalytics:
    def test_trend_by_day_month_year(self, auth_client):
        card = _account(auth_client)
        _tx(auth_client, card["id"], 10_00)
        _tx(auth_client, card["id"], 5_00, type_="income")
        days = auth_client.get("/api/v1/analytics/trend/?granularity=day").json()
        assert len(days) == 7
        assert days[-1] == {
            "start": TODAY.isoformat(),
            "income": days[-1]["income"] | {"minor": 5_00},
            "expense": days[-1]["expense"] | {"minor": 10_00},
        }
        assert len(auth_client.get("/api/v1/analytics/trend/?granularity=month").json()) == 6
        years = auth_client.get("/api/v1/analytics/trend/?granularity=year").json()
        assert [y["start"][:4] for y in years] == [str(TODAY.year - n) for n in (2, 1, 0)]
        ranged = auth_client.get(
            "/api/v1/analytics/trend/?granularity=day&date_from=2026-03-01&date_to=2026-03-02"
        ).json()
        assert [d["start"] for d in ranged] == ["2026-03-01", "2026-03-02"]
        bad = auth_client.get("/api/v1/analytics/trend/?granularity=week")
        assert bad.json()["errors"] == {"granularity": "invalid_choice"}

    def test_by_category_rolls_up_to_top_level(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client, "Еда")
        cafe = _category(auth_client, "Кафе", parent_id=food["id"], color="cat-cafe")
        _tx(auth_client, card["id"], 10_00, category_id=food["id"])
        _tx(auth_client, card["id"], 30_00, category_id=cafe["id"])
        rows = auth_client.get("/api/v1/analytics/by-category/").json()
        assert len(rows) == 1
        assert rows[0]["category"] == {
            "id": food["id"],
            "name": "Еда",
            "icon": "cart",
            "color": "cat-food",
        }
        assert rows[0]["amount"]["minor"] == 40_00


# ---------------------------------------------------------------------------
# R-100, R-101: notifications
# ---------------------------------------------------------------------------
class TestNotifications:
    def test_structured_fields_and_mark_one_read(self, auth_client, user):
        older = Notification.objects.create(
            user=user, type="budget_almost_spent", subject="Еда", percent=90
        )
        newer = Notification.objects.create(
            user=user, type="income_received", subject="ООО Ромашка", amount_minor=50000_00
        )
        items = auth_client.get("/api/v1/notifications/").json()
        assert [n["id"] for n in items] == [str(newer.id), str(older.id)]
        assert items[0]["subject"] == "ООО Ромашка"
        assert items[0]["amount_minor"] == 50000_00
        assert items[1]["percent"] == 90
        assert items[0]["created_at"]
        assert _post(auth_client, f"/api/v1/notifications/{older.id}/read/", {}).status_code == 200
        older.refresh_from_db()
        newer.refresh_from_db()
        assert (older.is_read, newer.is_read) == (True, False)

    def test_unknown_notification(self, auth_client):
        resp = _post(
            auth_client, "/api/v1/notifications/00000000-0000-0000-0000-000000000000/read/", {}
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "notification_not_found"
