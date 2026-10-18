"""Django ORM implementations of the accounts ports."""

from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError

from accounts.application.ports import ProfileRepository, UserRepository
from accounts.domain.entities import Profile, User
from accounts.domain.exceptions import EmailAlreadyTakenError
from accounts.domain.value_objects import Email
from accounts.infrastructure.mappers import (
    profile_to_domain,
    profile_to_orm,
    user_to_domain,
    user_to_orm,
)
from accounts.infrastructure.orm.models import Profile as ProfileORM
from accounts.infrastructure.orm.models import User as UserORM


class DjangoUserRepository(UserRepository):
    def add(self, user: User, password_hash: str) -> User:
        try:
            user_to_orm(user, password_hash).save(force_insert=True)
        except IntegrityError as exc:
            raise EmailAlreadyTakenError from exc
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        orm = UserORM.objects.filter(pk=user_id).first()
        return user_to_domain(orm) if orm else None

    def get_by_email(self, email: Email) -> User | None:
        orm = UserORM.objects.filter(email=email.value).first()
        return user_to_domain(orm) if orm else None

    def email_exists(self, email: Email) -> bool:
        return UserORM.objects.filter(email=email.value).exists()

    def update(self, user: User) -> User:
        orm = UserORM.objects.get(pk=user.id)
        orm.first_name = user.first_name
        orm.email = user.email.value
        orm.save(update_fields=["first_name", "email"])
        return user

    def get_password_hash(self, user_id: UUID) -> str | None:
        orm = UserORM.objects.filter(pk=user_id).first()
        return orm.password if orm else None

    def set_password(self, user_id: UUID, password_hash: str) -> None:
        orm = UserORM.objects.get(pk=user_id)
        orm.password = password_hash
        orm.save(update_fields=["password"])


class DjangoProfileRepository(ProfileRepository):
    def add(self, profile: Profile) -> Profile:
        profile_to_orm(profile).save(force_insert=True)
        return profile

    def get_by_user(self, user_id: UUID) -> Profile | None:
        orm = ProfileORM.objects.filter(user_id=user_id).first()
        return profile_to_domain(orm) if orm else None

    def update(self, profile: Profile) -> Profile:
        ProfileORM.objects.filter(pk=profile.user_id).update(
            base_currency=profile.base_currency.value,
            theme=profile.theme.value,
            onboarded=profile.onboarded,
            notify_budget=profile.notify_budget,
            notify_goal=profile.notify_goal,
            notify_recurring=profile.notify_recurring,
            notify_weekly_report=profile.notify_weekly_report,
        )
        return profile
