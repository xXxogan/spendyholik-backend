"""B-22: email confirmation and password change by a mailed code."""

from __future__ import annotations

import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from accounts.infrastructure.orm.models import User, VerificationCode

pytestmark = pytest.mark.django_db

PASSWORD = "password123"


def _code(message) -> str:
    return re.search(r"\b\d{6}\b", message.body).group()


@pytest.fixture
def mailed(django_capture_on_commit_callbacks):
    """Run on-commit callbacks (the mail is sent after the transaction commits)."""

    def run(call):
        with django_capture_on_commit_callbacks(execute=True):
            return call()

    return run


def _register(mailed, email="new@b.co"):
    client = APIClient()
    resp = mailed(
        lambda: client.post(
            "/api/v1/auth/register/",
            {"email": email, "password": PASSWORD, "personal_data_consent": True},
            format="json",
        )
    )
    assert resp.status_code == 201
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")
    return client, resp.json()


class TestEmailConfirmation:
    def test_new_account_is_closed_until_the_code_is_entered(self, mailed):
        client, body = _register(mailed)
        assert body["user"]["email_verified"] is False
        assert mail.outbox[-1].to == ["new@b.co"]
        blocked = client.get("/api/v1/accounts/")
        assert blocked.status_code == 403
        assert blocked.json()["code"] == "email_not_verified"
        profile = client.get("/api/v1/profile/")
        assert profile.status_code == 200
        assert profile.json()["email_verified"] is False
        confirmed = client.post(
            "/api/v1/auth/email/confirm/", {"code": _code(mail.outbox[-1])}, format="json"
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["email_verified"] is True
        assert client.get("/api/v1/accounts/").status_code == 200
        assert not VerificationCode.objects.exists()

    def test_wrong_code_and_attempt_limit(self, mailed):
        client, _ = _register(mailed)
        for _ in range(4):
            resp = client.post("/api/v1/auth/email/confirm/", {"code": "x"}, format="json")
            assert resp.json()["errors"] == {"code": "invalid_code"}
        resp = client.post("/api/v1/auth/email/confirm/", {"code": "x"}, format="json")
        assert resp.status_code == 429
        assert resp.json()["errors"] == {"code": "too_many_attempts"}
        assert VerificationCode.objects.get().attempts == 5

    def test_resend_is_rate_limited(self, mailed):
        client, _ = _register(mailed)
        resp = client.post("/api/v1/auth/email/resend/", format="json")
        assert resp.status_code == 429
        assert resp.json()["code"] == "resend_too_soon"
        VerificationCode.objects.update(sent_at="2000-01-01T00:00:00Z")
        mail.outbox.clear()
        assert mailed(lambda: client.post("/api/v1/auth/email/resend/")).status_code == 200
        assert len(mail.outbox) == 1

    def test_confirmed_account_cannot_confirm_again(self, auth_client):
        resp = auth_client.post("/api/v1/auth/email/resend/", format="json")
        assert resp.status_code == 409
        assert resp.json()["code"] == "email_already_verified"

    def test_new_email_needs_confirmation(self, auth_client, user, mailed):
        resp = mailed(
            lambda: auth_client.patch(
                "/api/v1/profile/",
                {"email": "moved@b.co", "current_password": "password123"},
                format="json",
            )
        )
        assert resp.json()["email_verified"] is False
        assert [m.to for m in mail.outbox[-2:]] == [["moved@b.co"], [user.email]]
        assert "moved@b.co" in mail.outbox[-1].body
        assert auth_client.get("/api/v1/goals/").status_code == 403


class TestPasswordChange:
    def test_change_with_the_mailed_code(self, auth_client, user, mailed):
        assert mailed(lambda: auth_client.post("/api/v1/profile/password/code/")).status_code == 200
        message = mail.outbox[-1]
        assert message.to == [user.email]
        resp = auth_client.patch(
            "/api/v1/profile/password/",
            {"code": _code(message), "new_password": "Brand-new-pass1"},
            format="json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password("Brand-new-pass1")

    def test_old_password_is_no_longer_accepted(self, auth_client):
        resp = auth_client.patch(
            "/api/v1/profile/password/",
            {"old_password": "password123", "new_password": "Brand-new-pass1"},
            format="json",
        )
        assert resp.status_code == 422
        assert resp.json()["errors"] == {"code": "required"}

    def test_unconfirmed_user_cannot_change_the_password(self, mailed):
        client, _ = _register(mailed, "u@b.co")
        assert client.post("/api/v1/profile/password/code/").status_code == 403
        assert User.objects.get(email="u@b.co").email_verified is False


def test_code_endpoints_are_throttled(auth_client, monkeypatch):
    from django.core.cache import cache
    from rest_framework.throttling import ScopedRateThrottle

    cache.clear()
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"codes": "2/hour"})
    for _ in range(2):
        auth_client.post("/api/v1/auth/email/confirm/", {"code": "1"}, format="json")
    resp = auth_client.post("/api/v1/auth/email/confirm/", {"code": "1"}, format="json")
    assert resp.status_code == 429
    assert resp.json()["code"] == "throttled"


def test_attempts_are_reserved_in_the_database(mailed):
    client, _ = _register(mailed, "race@b.co")
    from accounts.infrastructure.repositories import DjangoVerificationCodeRepository

    code = VerificationCode.objects.get()
    repo = DjangoVerificationCodeRepository()
    assert all(repo.reserve_attempt(code.id, 5) for _ in range(5))
    assert repo.reserve_attempt(code.id, 5) is False
    resp = client.post(
        "/api/v1/auth/email/confirm/", {"code": _code(mail.outbox[-1])}, format="json"
    )
    assert resp.json()["errors"] == {"code": "too_many_attempts"}


def test_broker_outage_does_not_fail_registration(mailed, monkeypatch):
    from kombu.exceptions import OperationalError

    from tasks.tasks import send_email

    def down(*args, **kwargs):
        raise OperationalError("redis is down")

    monkeypatch.setattr(send_email, "apply_async", down)
    client, body = _register(mailed, "outage@b.co")
    assert body["user"]["email"] == "outage@b.co"
    assert User.objects.filter(email="outage@b.co").exists()


def test_mail_task_does_not_retry_refused_recipients():
    import smtplib

    from tasks.tasks import send_email

    assert smtplib.SMTPRecipientsRefused in send_email.dont_autoretry_for
    assert send_email.max_retries == 3
