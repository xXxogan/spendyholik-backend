"""Regression tests for the backend review fixes."""

from __future__ import annotations

from datetime import date

import pytest
from django.core import mail
from rest_framework.test import APIClient

from finances.infrastructure.orm.models import Category
from tests.factories import UserFactory

pytestmark = [pytest.mark.api, pytest.mark.django_db]

PASSWORD = "Str0ng-Passw0rd"


def _account(client, currency="RUB"):
    return client.post(
        "/api/v1/accounts/",
        {"name": f"Счёт {currency}", "type": "debit", "currency": currency},
        format="json",
    ).json()


def _register(email="a@b.co"):
    client = APIClient()
    body = client.post(
        "/api/v1/auth/register/", {"email": email, "password": PASSWORD}, format="json"
    ).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    return client, body["refresh"]


class TestAmounts:
    @pytest.mark.parametrize("amount", [0, -5000])
    def test_transaction_amount_must_be_positive(self, auth_client, amount):
        acct = _account(auth_client)
        resp = auth_client.post(
            "/api/v1/transactions/",
            {
                "account_id": acct["id"],
                "type": "expense",
                "amount_minor": amount,
                "date": "2026-11-01",
            },
            format="json",
        )
        assert resp.status_code == 422

    def test_recurring_amount_must_be_positive(self, auth_client):
        acct = _account(auth_client)
        resp = auth_client.post(
            "/api/v1/recurring/",
            {
                "name": "R",
                "amount_minor": -100,
                "type": "expense",
                "account_id": acct["id"],
                "frequency": "monthly",
                "next_run": "2026-11-01",
            },
            format="json",
        )
        assert resp.status_code == 422


class TestRecurringValidation:
    def _payload(self, acct_id, **extra):
        return {
            "name": "R",
            "amount_minor": 100,
            "type": "expense",
            "account_id": acct_id,
            "frequency": "monthly",
            "next_run": "2026-11-01",
            **extra,
        }

    def test_rejects_foreign_category(self, auth_client):
        other = UserFactory(password="x" * 12)
        foreign = Category.objects.create(user=other, name="SECRET", type="expense")
        acct = _account(auth_client)
        resp = auth_client.post(
            "/api/v1/recurring/",
            self._payload(acct["id"], category_id=str(foreign.id)),
            format="json",
        )
        assert resp.status_code == 404

    def test_rejects_category_of_wrong_type(self, auth_client):
        acct = _account(auth_client)
        income = auth_client.post(
            "/api/v1/categories/", {"name": "Зарплата", "type": "income"}, format="json"
        ).json()
        resp = auth_client.post(
            "/api/v1/recurring/", self._payload(acct["id"], category_id=income["id"]), format="json"
        )
        assert resp.status_code == 422

    def test_rejects_transfer_templates(self, auth_client):
        acct = _account(auth_client)
        resp = auth_client.post(
            "/api/v1/recurring/", self._payload(acct["id"], type="transfer"), format="json"
        )
        assert resp.status_code == 422


class TestTokens:
    def test_invalid_refresh_token_returns_401(self, api_client):
        resp = api_client.post("/api/v1/auth/refresh/", {"refresh_token": "garbage"}, format="json")
        assert resp.status_code == 401
        assert resp.json()["code"] == "token_invalid"

    def test_reused_refresh_token_returns_401(self):
        client, refresh = _register()
        assert (
            client.post(
                "/api/v1/auth/refresh/", {"refresh_token": refresh}, format="json"
            ).status_code
            == 200
        )
        resp = client.post("/api/v1/auth/refresh/", {"refresh_token": refresh}, format="json")
        assert resp.status_code == 401

    def test_invalid_logout_token_returns_401(self, api_client):
        resp = api_client.post("/api/v1/auth/logout/", {"refresh_token": "garbage"}, format="json")
        assert resp.status_code == 401

    def test_change_password_revokes_refresh_tokens(self):
        client, refresh = _register()
        resp = client.patch(
            "/api/v1/profile/password/",
            {"old_password": PASSWORD, "new_password": "An0ther-Passw0rd"},
            format="json",
        )
        assert resp.status_code in (200, 204)
        resp = client.post("/api/v1/auth/refresh/", {"refresh_token": refresh}, format="json")
        assert resp.status_code == 401


class TestPasswordReset:
    def test_reset_token_is_emailed_and_revokes_sessions(self, api_client):
        _, refresh = _register("reset@b.co")
        resp = api_client.post(
            "/api/v1/auth/password/reset/", {"email": "reset@b.co"}, format="json"
        )
        assert resp.status_code in (200, 202)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["reset@b.co"]
        token = mail.outbox[0].body.split("\n\n")[1].strip()

        resp = api_client.post(
            "/api/v1/auth/password/confirm/",
            {"token": token, "new_password": "An0ther-Passw0rd"},
            format="json",
        )
        assert resp.status_code in (200, 204)
        resp = api_client.post(
            "/api/v1/auth/login/",
            {"email": "reset@b.co", "password": "An0ther-Passw0rd"},
            format="json",
        )
        assert resp.status_code == 200
        resp = api_client.post("/api/v1/auth/refresh/", {"refresh_token": refresh}, format="json")
        assert resp.status_code == 401

    def test_unknown_email_sends_nothing(self, api_client):
        resp = api_client.post(
            "/api/v1/auth/password/reset/", {"email": "nobody@b.co"}, format="json"
        )
        assert resp.status_code in (200, 202)
        assert mail.outbox == []


class TestCategoryWithBudget:
    def test_delete_is_refused_while_budgets_exist(self, auth_client):
        cat = auth_client.post(
            "/api/v1/categories/", {"name": "Еда", "type": "expense"}, format="json"
        ).json()
        budget = auth_client.post(
            "/api/v1/budgets/", {"category_id": cat["id"], "amount_minor": 1000_00}, format="json"
        ).json()
        assert auth_client.delete(f"/api/v1/categories/{cat['id']}/").status_code == 409
        assert auth_client.get(f"/api/v1/budgets/{budget['id']}/").status_code == 200


class TestGoalContributionCurrency:
    def test_rejects_account_in_other_currency(self, auth_client):
        rub = _account(auth_client, "RUB")
        usd = _account(auth_client, "USD")
        goal = auth_client.post(
            "/api/v1/goals/",
            {
                "name": "Подушка",
                "target_amount_minor": 100000_00,
                "currency": "RUB",
                "account_id": rub["id"],
            },
            format="json",
        ).json()
        resp = auth_client.post(
            f"/api/v1/goals/{goal['id']}/contribute/",
            {"account_id": usd["id"], "amount_minor": 100_00, "date": "2026-11-01"},
            format="json",
        )
        assert resp.status_code == 422


class TestCsvExport:
    def test_exports_every_page(self, user, tmp_path, settings):
        from finances.infrastructure.orm.models import Account, Transaction
        from tasks.tasks import generate_csv_export

        settings.MEDIA_ROOT = tmp_path
        acct = Account.objects.create(user=user, name="A", type="debit", currency="RUB")
        Transaction.objects.bulk_create(
            Transaction(user=user, account=acct, type="expense", amount=1, date=date(2026, 1, 1))
            for _ in range(150)
        )
        key = generate_csv_export(str(user.id))
        rows = (tmp_path / key).read_text().splitlines()
        assert len(rows) == 151  # header + every transaction
