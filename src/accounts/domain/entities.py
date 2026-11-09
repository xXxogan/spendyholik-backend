"""Domain entities for the accounts bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from accounts.domain.enums import CodePurpose, Theme
from accounts.domain.value_objects import Email
from shared.domain.currency_code import CurrencyCode


@dataclass(frozen=True, slots=True)
class User:
    email: Email
    first_name: str = ""
    #: False until the user enters the code mailed to ``email``.
    email_verified: bool = True
    #: When the user consented to the processing of personal data (152-FZ art. 9).
    personal_data_consent_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class Profile:
    user_id: UUID
    base_currency: CurrencyCode = CurrencyCode("RUB")
    theme: Theme = Theme.AUTO
    onboarded: bool = False
    notify_budget: bool = True
    notify_goal: bool = True
    notify_recurring: bool = True
    notify_income: bool = True
    notify_weekly_report: bool = True


@dataclass(frozen=True, slots=True)
class VerificationCode:
    """A one-time code mailed to the user; only its hash is stored."""

    user_id: UUID
    purpose: CodePurpose
    code_hash: str
    sent_at: datetime
    expires_at: datetime
    attempts: int = 0
    #: Codes of this user and purpose mailed on the day of ``sent_at`` (UTC).
    sent_count: int = 1
    id: UUID = field(default_factory=uuid4)
