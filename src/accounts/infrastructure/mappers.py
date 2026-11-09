"""ORM ↔ domain mappers for the accounts bounded context."""

from __future__ import annotations

from accounts.domain.entities import Profile, User
from accounts.domain.enums import Theme
from accounts.domain.value_objects import Email
from accounts.infrastructure.orm.models import Profile as ProfileORM
from accounts.infrastructure.orm.models import User as UserORM
from shared.domain.currency_code import CurrencyCode


def user_to_domain(orm: UserORM) -> User:
    return User(
        email=Email(orm.email),
        first_name=orm.first_name,
        email_verified=orm.email_verified,
        personal_data_consent_at=orm.personal_data_consent_at,
        id=orm.id,
    )


def user_to_orm(user: User, password_hash: str | None = None) -> UserORM:
    orm = UserORM(
        id=user.id,
        email=user.email.value,
        first_name=user.first_name,
        email_verified=user.email_verified,
        personal_data_consent_at=user.personal_data_consent_at,
    )
    if password_hash is not None:
        orm.password = password_hash
    return orm


def profile_to_domain(orm: ProfileORM) -> Profile:
    return Profile(
        user_id=orm.user_id,
        base_currency=CurrencyCode(orm.base_currency),
        theme=Theme(orm.theme),
        onboarded=orm.onboarded,
        notify_budget=orm.notify_budget,
        notify_goal=orm.notify_goal,
        notify_recurring=orm.notify_recurring,
        notify_income=orm.notify_income,
        notify_weekly_report=orm.notify_weekly_report,
    )


def profile_to_orm(profile: Profile) -> ProfileORM:
    return ProfileORM(
        user_id=profile.user_id,
        base_currency=profile.base_currency.value,
        theme=profile.theme.value,
        onboarded=profile.onboarded,
        notify_budget=profile.notify_budget,
        notify_goal=profile.notify_goal,
        notify_recurring=profile.notify_recurring,
        notify_income=profile.notify_income,
        notify_weekly_report=profile.notify_weekly_report,
    )
