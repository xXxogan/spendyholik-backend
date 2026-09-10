"""Accounts gateway implementations (password hashing, JWT, reset tokens, social)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.application.ports import (
    AuthTokenService,
    PasswordHasher,
    PasswordResetGateway,
    SocialIdentity,
    SocialIdentityProvider,
    TokenPair,
    UserRepository,
)
from accounts.domain.entities import User
from accounts.infrastructure.orm.models import User as UserORM


class DjangoPasswordHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return make_password(password)

    def verify(self, password: str, hashed: str) -> bool:
        return check_password(password, hashed)


def _to_datetime(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


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

    def refresh(self, refresh_token: str) -> TokenPair:
        token = RefreshToken(refresh_token)
        user_id = token["user_id"]
        token.blacklist()
        orm = UserORM.objects.get(pk=user_id)
        new_refresh = RefreshToken.for_user(orm)
        return TokenPair(
            access=str(new_refresh.access_token),
            refresh=str(new_refresh),
            access_expires_at=_to_datetime(new_refresh.access_token["exp"]),
            refresh_expires_at=_to_datetime(new_refresh["exp"]),
        )

    def revoke(self, refresh_token: str) -> None:
        RefreshToken(refresh_token).blacklist()


class DjangoCachePasswordResetGateway(PasswordResetGateway):
    """Stores one-time reset tokens in the cache (Redis) with a TTL."""

    timeout_seconds = 60 * 60  # 1 hour

    def _key(self, token: str) -> str:
        return f"password-reset:{token}"

    def issue_token(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        cache.set(self._key(token), str(user.id), timeout=self.timeout_seconds)
        return token

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
