"""Domain entities for the accounts bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from accounts.domain.enums import Theme
from accounts.domain.value_objects import Email
from shared.domain.currency_code import CurrencyCode


@dataclass(frozen=True, slots=True)
class User:
    email: Email
    first_name: str = ""
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
    notify_weekly_report: bool = True
