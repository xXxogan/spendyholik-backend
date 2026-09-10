"""Ports (abstract interfaces) for the accounts bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from accounts.domain.entities import Profile, User
from accounts.domain.value_objects import Email


class UserRepository(ABC):
    @abstractmethod
    def add(self, user: User, password_hash: str) -> User: ...

    @abstractmethod
    def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: Email) -> User | None: ...

    @abstractmethod
    def email_exists(self, email: Email) -> bool: ...

    @abstractmethod
    def update(self, user: User) -> User: ...

    @abstractmethod
    def get_password_hash(self, user_id: UUID) -> str | None: ...

    @abstractmethod
    def set_password(self, user_id: UUID, password_hash: str) -> None: ...


class ProfileRepository(ABC):
    @abstractmethod
    def add(self, profile: Profile) -> Profile: ...

    @abstractmethod
    def get_by_user(self, user_id: UUID) -> Profile | None: ...

    @abstractmethod
    def update(self, profile: Profile) -> Profile: ...


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: str
    refresh: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class AuthTokenService(ABC):
    """Issues/validates JWT token pairs (implemented by SimpleJWT in infrastructure)."""

    @abstractmethod
    def issue(self, user: User) -> TokenPair: ...

    @abstractmethod
    def refresh(self, refresh_token: str) -> TokenPair: ...

    @abstractmethod
    def revoke(self, refresh_token: str) -> None: ...


class PasswordResetGateway(ABC):
    """Generates one-time reset tokens and delivers them (usually by email)."""

    @abstractmethod
    def issue_token(self, user: User) -> str: ...

    @abstractmethod
    def resolve_token(self, token: str) -> UUID | None: ...

    @abstractmethod
    def invalidate_token(self, token: str) -> None: ...


class SocialIdentityProvider(ABC):
    """Exchanges an external OAuth credential for a verified identity."""

    @abstractmethod
    def exchange(self, provider: str, credential: str) -> "SocialIdentity | None": ...


@dataclass(frozen=True, slots=True)
class SocialIdentity:
    provider: str
    email: Email
    first_name: str
