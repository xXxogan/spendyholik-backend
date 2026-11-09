"""Django ORM implementations of the accounts ports."""

from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, models, transaction

from accounts.application.codes import RESEND_COOLDOWN
from accounts.application.ports import (
    ProfileRepository,
    UserRepository,
    VerificationCodeRepository,
)
from accounts.domain.entities import Profile, User, VerificationCode
from accounts.domain.enums import CodePurpose
from accounts.domain.exceptions import EmailAlreadyTakenError, ResendTooSoonError
from accounts.domain.value_objects import Email
from accounts.infrastructure.mappers import (
    profile_to_domain,
    profile_to_orm,
    user_to_domain,
    user_to_orm,
)
from accounts.infrastructure.orm.models import Profile as ProfileORM
from accounts.infrastructure.orm.models import User as UserORM
from accounts.infrastructure.orm.models import VerificationCode as VerificationCodeORM


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
        orm.email_verified = user.email_verified
        orm.personal_data_consent_at = user.personal_data_consent_at
        fields = ["first_name", "email", "email_verified", "personal_data_consent_at"]
        try:
            with transaction.atomic():
                orm.save(update_fields=fields)
        except IntegrityError as exc:
            raise EmailAlreadyTakenError from exc
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
            notify_income=profile.notify_income,
            notify_weekly_report=profile.notify_weekly_report,
        )
        return profile


def _code_to_domain(orm: VerificationCodeORM) -> VerificationCode:
    return VerificationCode(
        id=orm.id,
        user_id=orm.user_id,
        purpose=CodePurpose(orm.purpose),
        code_hash=orm.code_hash,
        sent_at=orm.sent_at,
        expires_at=orm.expires_at,
        attempts=orm.attempts,
        sent_count=orm.sent_count,
    )


class DjangoVerificationCodeRepository(VerificationCodeRepository):
    def replace(self, code: VerificationCode) -> VerificationCode:
        try:
            with transaction.atomic():
                VerificationCodeORM.objects.filter(
                    user_id=code.user_id, purpose=code.purpose.value
                ).delete()
                VerificationCodeORM.objects.create(
                    id=code.id,
                    user_id=code.user_id,
                    purpose=code.purpose.value,
                    code_hash=code.code_hash,
                    sent_at=code.sent_at,
                    expires_at=code.expires_at,
                    attempts=code.attempts,
                    sent_count=code.sent_count,
                )
        except IntegrityError as exc:
            # A parallel request mailed a code a moment ago.
            raise ResendTooSoonError(int(RESEND_COOLDOWN.total_seconds())) from exc
        return code

    def get_live(self, user_id: UUID, purpose: CodePurpose) -> VerificationCode | None:
        orm = VerificationCodeORM.objects.filter(user_id=user_id, purpose=purpose.value).first()
        return _code_to_domain(orm) if orm else None

    def reserve_attempt(self, code_id: UUID, limit: int) -> bool:
        reserved = VerificationCodeORM.objects.filter(pk=code_id, attempts__lt=limit).update(
            attempts=models.F("attempts") + 1
        )
        return reserved > 0

    def delete(self, code_id: UUID) -> None:
        VerificationCodeORM.objects.filter(pk=code_id).delete()

    def delete_for(self, user_id: UUID, purpose: CodePurpose) -> None:
        VerificationCodeORM.objects.filter(user_id=user_id, purpose=purpose.value).delete()
