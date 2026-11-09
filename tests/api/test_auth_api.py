"""API contract tests for authentication."""

from __future__ import annotations

import pytest

from accounts.infrastructure.orm.models import User


@pytest.mark.django_db
class TestRegisterAndLogin:
    def test_register_returns_tokens_and_minor_free_payload(self, api_client):
        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "new@example.com",
                "password": "password123",
                "first_name": "Ann",
                "personal_data_consent": True,
            },
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
            {"email": user.email, "password": "password123", "personal_data_consent": True},
            format="json",
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "email_already_taken"

    def test_login_success(self, api_client, user):
        resp = api_client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "password123", "personal_data_consent": True},
            format="json",
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

        resp = auth_client.patch(
            "/api/v1/profile/", {"onboarded": True, "theme": "dark"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["onboarded"] is True
        assert resp.json()["theme"] == "dark"


@pytest.mark.django_db
class TestPersonalDataConsent:
    def test_registration_needs_consent(self, api_client):
        resp = api_client.post(
            "/api/v1/auth/register/",
            {"email": "no@example.com", "password": "password123"},
            format="json",
        )
        assert resp.status_code == 422
        assert resp.json()["errors"] == {"personal_data_consent": "required"}
        assert not User.objects.filter(email="no@example.com").exists()

    def test_consent_time_is_stored_and_shown(self, api_client):
        body = api_client.post(
            "/api/v1/auth/register/",
            {"email": "yes@example.com", "password": "password123", "personal_data_consent": True},
            format="json",
        ).json()
        assert User.objects.get(email="yes@example.com").personal_data_consent_at is not None
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        profile = api_client.get("/api/v1/profile/").json()
        assert profile["personal_data_consent_at"]


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["yes", "true", 1])
def test_consent_must_be_a_real_true(api_client, value):
    resp = api_client.post(
        "/api/v1/auth/register/",
        {"email": "lax@example.com", "password": "password123", "personal_data_consent": value},
        format="json",
    )
    assert resp.status_code == 422
    assert resp.json()["errors"] == {"personal_data_consent": "invalid"}
