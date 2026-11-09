"""Input/output DTOs for the accounts application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from accounts.domain.enums import Theme


# ---------------------------------------------------------------------------
# Input DTOs (pydantic — validated at the use-case boundary)
# ---------------------------------------------------------------------------
class RegisterUserInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(default="", max_length=150)
    #: Explicit consent to personal data processing; must be JSON ``true``
    #: (152-FZ art. 9) — "yes", 1 or "true" are rejected.
    personal_data_consent: StrictBool = False


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

    first_name: str | None = Field(default=None, max_length=150)
    email: str | None = None
    #: Required with a new ``email``: a stolen session alone must not move the account.
    current_password: str | None = Field(default=None, max_length=128)
    base_currency: str | None = None
    theme: Theme | None = None
    onboarded: bool | None = None
    notify_budget: bool | None = None
    notify_goal: bool | None = None
    notify_recurring: bool | None = None
    notify_income: bool | None = None
    notify_weekly_report: bool | None = None


class ChangePasswordInput(BaseModel):
    """A new password, confirmed by the code from ``POST profile/password/code/``."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1, max_length=12)
    new_password: str = Field(min_length=8, max_length=128)


class ConfirmEmailInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1, max_length=12)


# ---------------------------------------------------------------------------
# Output DTOs (dataclasses — consumed by the interfaces layer)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UserDTO:
    id: UUID
    email: str
    first_name: str
    email_verified: bool = True


@dataclass(frozen=True, slots=True)
class ProfileDTO:
    user_id: UUID
    first_name: str
    email: str
    email_verified: bool
    personal_data_consent_at: datetime | None
    base_currency: str
    theme: Theme
    onboarded: bool
    notify_budget: bool
    notify_goal: bool
    notify_recurring: bool
    notify_income: bool
    notify_weekly_report: bool


@dataclass(frozen=True, slots=True)
class AuthResultDTO:
    user: UserDTO
    tokens: object  # TokenPair


@dataclass(frozen=True, slots=True)
class PasswordResetRequestedDTO:
    acknowledged: bool
