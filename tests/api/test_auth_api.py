"""API contract tests for authentication."""

from __future__ import annotations

import pytest

from accounts.infrastructure.orm.models import User


@pytest.mark.django_db
class TestRegisterAndLogin:
    def test_register_returns_tokens_and_minor_free_payload(self, api_client):
        resp = api_client.post(
            "/api/v1/auth/register/",
            {"email": "new@example.com", "password": "password123", "first_name": "Ann"},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user"]["email"] == "new@example.com"
        assert data["access"]
        assert data["refresh"]
        assert User.objects.filter(email="new@example.com").exists()

    def test_duplicate_email_returns_409(self, api_client, user):
        resp = api_client.post(
            "/api/v1/auth/register/",
            {"email": user.email, "password": "password123"},
            format="json",
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "email_already_taken"

    def test_login_success(self, api_client, user):
        resp = api_client.post(
            "/api/v1/auth/login/", {"email": user.email, "password": "password123"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["access"]

    def test_login_wrong_password_returns_401(self, api_client, user):
        resp = api_client.post(
            "/api/v1/auth/login/", {"email": user.email, "password": "wrongpass"}, format="json"
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "invalid_credentials"

    def test_short_password_returns_422(self, api_client):
        resp = api_client.post(
            "/api/v1/auth/register/", {"email": "x@example.com", "password": "short"}, format="json"
        )
        assert resp.status_code == 422


@pytest.mark.django_db
class TestProfile:
    def test_profile_requires_auth(self, api_client):
        resp = api_client.get("/api/v1/profile/")
        assert resp.status_code == 401

    def test_get_and_update_profile(self, auth_client):
        resp = auth_client.get("/api/v1/profile/")
        assert resp.status_code == 200
        assert resp.json()["base_currency"] == "RUB"

        resp = auth_client.patch("/api/v1/profile/", {"onboarded": True, "theme": "dark"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["onboarded"] is True
        assert resp.json()["theme"] == "dark"
