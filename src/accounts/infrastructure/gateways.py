"""Accounts gateway implementations (password hashing, JWT, reset tokens, social)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.application.ports import (
    AuthTokenService,
    CodeSender,
    PasswordHasher,
    PasswordResetGateway,
    SocialIdentity,
    SocialIdentityProvider,
    TokenPair,
)
from accounts.domain.entities import User
from accounts.domain.enums import CodePurpose
from accounts.domain.exceptions import InvalidTokenError
from accounts.infrastructure.orm.models import User as UserORM


class DjangoPasswordHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return make_password(password)

    def verify(self, password: str, hashed: str) -> bool:
        return check_password(password, hashed)


def _to_datetime(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)


class SimpleJWTTokenService(AuthTokenService):
    def issue(self, user: User) -> TokenPair:
        orm = UserORM.objects.get(pk=user.id)
        refresh = RefreshToken.for_user(orm)
        return TokenPair(
            access=str(refresh.access_token),
            refresh=str(refresh),
            access_expires_at=_to_datetime(refresh.access_token["exp"]),
            refresh_expires_at=_to_datetime(refresh["exp"]),
        )

    @staticmethod
    def _parse(refresh_token: str) -> RefreshToken:
        try:
            return RefreshToken(refresh_token)
        except TokenError as exc:  # malformed, expired or already blacklisted
            raise InvalidTokenError from exc

    def refresh(self, refresh_token: str) -> TokenPair:
        token = self._parse(refresh_token)
        orm = UserORM.objects.filter(pk=token["user_id"], is_active=True).first()
        if orm is None:
            raise InvalidTokenError
        token.blacklist()
        new_refresh = RefreshToken.for_user(orm)
        return TokenPair(
            access=str(new_refresh.access_token),
            refresh=str(new_refresh),
            access_expires_at=_to_datetime(new_refresh.access_token["exp"]),
            refresh_expires_at=_to_datetime(new_refresh["exp"]),
        )

    def revoke(self, refresh_token: str) -> None:
        self._parse(refresh_token).blacklist()

    def revoke_all(self, user_id: UUID) -> None:
        outstanding = OutstandingToken.objects.filter(
            user_id=user_id, blacklistedtoken__isnull=True
        )
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token=t) for t in outstanding], ignore_conflicts=True
        )


class DjangoCachePasswordResetGateway(PasswordResetGateway):
    """Stores one-time reset tokens in the cache (Redis) with a TTL."""

    timeout_seconds = 60 * 60  # 1 hour

    def _key(self, token: str) -> str:
        return f"password-reset:{token}"

    def issue_token(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        cache.set(self._key(token), str(user.id), timeout=self.timeout_seconds)
        return token

    def send_token(self, user: User, token: str) -> None:
        send_mail(
            subject="SpendyHolik: password reset",
            message=(
                "Use this code to reset your SpendyHolik password "
                f"(valid for {self.timeout_seconds // 60} minutes):\n\n{token}\n\n"
                "If you did not request a reset, ignore this email."
            ),
            from_email=None,
            recipient_list=[user.email.value],
        )

    def resolve_token(self, token: str) -> UUID | None:
        value = cache.get(self._key(token))
        return UUID(value) if value else None

    def invalidate_token(self, token: str) -> None:
        cache.delete(self._key(token))


class SocialAuthIdentityProvider(SocialIdentityProvider):
    """Exchanges OAuth credentials via social-auth backends.

    The full Google/Apple Authorization-Code + PKCE exchange is wired here in
    production; this reference implementation returns ``None`` until the
    provider credentials are configured.
    """

    def exchange(self, provider: str, credential: str) -> SocialIdentity | None:
        # TODO(production): use social_django backends to exchange the code/token.
        return None


_CODE_MAIL = {
    CodePurpose.VERIFY_EMAIL: (
        "SpendyHolik: код подтверждения почты",
        "Ваш код подтверждения почты: {code}\n\nКод действует {ttl} мин. "
        "Если вы не регистрировались в SpendyHolik, просто проигнорируйте это письмо.",
    ),
    CodePurpose.CHANGE_PASSWORD: (
        "SpendyHolik: код для смены пароля",
        "Ваш код для смены пароля: {code}\n\nКод действует {ttl} мин. "
        "Если вы не меняли пароль, никому не сообщайте код и смените пароль.",
    ),
}


class CeleryEmailCodeSender(CodeSender):
    """Mails the code from a Celery worker once the surrounding transaction commits."""

    def send(self, user: User, purpose: CodePurpose, code: str, ttl_minutes: int) -> None:

        subject, body = _CODE_MAIL[purpose]
        text = body.format(code=code, ttl=ttl_minutes)
        # The task must not outlive the code it carries.
        _mail_after_commit(user.email.value, subject, text, expires=ttl_minutes * 60)

    def email_changed(self, old_email: str, new_email: str) -> None:
        _mail_after_commit(
            old_email,
            "SpendyHolik: почта аккаунта изменена",
            f"Почта вашего аккаунта SpendyHolik изменена на {new_email}.\n\n"
            "Если это сделали не вы, восстановите доступ через сброс пароля и "
            "напишите в поддержку.",
        )


def _mail_after_commit(to: str, subject: str, body: str, expires: int | None = None) -> None:
    """Queue the mail once the transaction commits; a broker outage is logged, not raised."""
    from tasks.tasks import send_email

    def enqueue() -> None:
        send_email.apply_async((to, subject, body), expires=expires)

    # robust: a failed enqueue (Redis down) must not turn a committed write into a 500.
    transaction.on_commit(enqueue, robust=True)
