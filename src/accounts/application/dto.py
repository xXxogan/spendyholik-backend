"""Input/output DTOs for the accounts application layer."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from accounts.domain.enums import Theme


# ---------------------------------------------------------------------------
# Input DTOs (pydantic — validated at the use-case boundary)
# ---------------------------------------------------------------------------
class RegisterUserInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(default="", max_length=150)


class LoginUserInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str
    password: str


class RefreshTokenInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    refresh_token: str


class LogoutUserInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    refresh_token: str


class RequestPasswordResetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str


class ConfirmPasswordResetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str
    new_password: str = Field(min_length=8, max_length=128)


class SocialLoginInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    credential: str


class UpdateProfileInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_currency: str | None = None
    theme: Theme | None = None
    onboarded: bool | None = None
    notify_budget: bool | None = None
    notify_goal: bool | None = None
    notify_recurring: bool | None = None
    notify_weekly_report: bool | None = None


class ChangePasswordInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Output DTOs (dataclasses — consumed by the interfaces layer)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UserDTO:
    id: UUID
    email: str
    first_name: str


@dataclass(frozen=True, slots=True)
class ProfileDTO:
    user_id: UUID
    base_currency: str
    theme: Theme
    onboarded: bool
    notify_budget: bool
    notify_goal: bool
    notify_recurring: bool
    notify_weekly_report: bool


@dataclass(frozen=True, slots=True)
class AuthResultDTO:
    user: UserDTO
    tokens: object  # TokenPair


@dataclass(frozen=True, slots=True)
class PasswordResetRequestedDTO:
    acknowledged: bool
