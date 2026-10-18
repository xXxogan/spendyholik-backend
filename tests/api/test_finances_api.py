"""API contract tests for the finances module."""

from __future__ import annotations

import pytest

from accounts.infrastructure.orm.models import Profile
from tests.factories import UserFactory


@pytest.mark.django_db
class TestAccounts:
    def test_create_account_uses_minor_units(self, auth_client):
        resp = auth_client.post(
            "/api/v1/accounts/",
            {"name": "Карта", "type": "debit", "currency": "RUB", "initial_balance_minor": 5000_00},
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["initial_balance"]["minor"] == 5000_00
        assert body["initial_balance"]["currency"] == "RUB"
        assert body["initial_balance"]["formatted"]

    def test_list_accounts(self, auth_client):
        auth_client.post(
            "/api/v1/accounts/", {"name": "A", "type": "debit", "currency": "RUB"}, format="json"
        )
        resp = auth_client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_ownership_isolation(self, auth_client, db):
        # Create an account for user A.
        auth_client.post(
            "/api/v1/accounts/", {"name": "A", "type": "debit", "currency": "RUB"}, format="json"
        )
        account_id = auth_client.get("/api/v1/accounts/").json()[0]["id"]

        # User B cannot see user A's account → 404 (not 403).
        other = UserFactory(password="password123")
        Profile.objects.get_or_create(user=other)
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        other_client = APIClient()
        refresh = RefreshToken.for_user(other)
        other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        resp = other_client.get(f"/api/v1/accounts/{account_id}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestTransactions:
    def test_create_transaction_minor_units_and_viewmodel(self, auth_client):
        acct = auth_client.post(
            "/api/v1/accounts/",
            {"name": "Карта", "type": "debit", "currency": "RUB"},
            format="json",
        ).json()
        cat = auth_client.post(
            "/api/v1/categories/", {"name": "Еда", "type": "expense"}, format="json"
        ).json()
        resp = auth_client.post(
            "/api/v1/transactions/",
            {
                "account_id": acct["id"],
                "category_id": cat["id"],
                "type": "expense",
                "amount_minor": 1240_00,
                "date": "2026-03-15",
            },
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["amount"]["minor"] == 1240_00
        assert body["title"] == "Еда"
        assert body["account"]["name"] == "Карта"

    def test_transfer_requires_destination(self, auth_client):
        acct = auth_client.post(
            "/api/v1/accounts/",
            {"name": "Карта", "type": "debit", "currency": "RUB"},
            format="json",
        ).json()
        resp = auth_client.post(
            "/api/v1/transactions/",
            {
                "account_id": acct["id"],
                "type": "transfer",
                "amount_minor": 100,
                "date": "2026-03-15",
            },
            format="json",
        )
        assert resp.status_code == 422

    def test_transaction_list_cursor(self, auth_client):
        acct = auth_client.post(
            "/api/v1/accounts/",
            {"name": "Карта", "type": "debit", "currency": "RUB"},
            format="json",
        ).json()
        for i in range(3):
            auth_client.post(
                "/api/v1/transactions/",
                {
                    "account_id": acct["id"],
                    "type": "expense",
                    "amount_minor": 100 + i,
                    "date": f"2026-03-{i + 1:02d}",
                },
                format="json",
            )
        resp = auth_client.get("/api/v1/transactions/?limit=2")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"]


@pytest.mark.django_db
class TestBudgets:
    def test_budget_requires_expense_category(self, auth_client):
        income = auth_client.post(
            "/api/v1/categories/", {"name": "Зарплата", "type": "income"}, format="json"
        ).json()
        resp = auth_client.post(
            "/api/v1/budgets/",
            {"category_id": income["id"], "amount_minor": 1000_00},
            format="json",
        )
        assert resp.status_code == 422
