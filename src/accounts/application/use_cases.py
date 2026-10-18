"""Use cases for the accounts bounded context (auth + profile)."""

from __future__ import annotations

import secrets
from uuid import UUID

from accounts.application.dto import (
    AuthResultDTO,
    ChangePasswordInput,
    ConfirmPasswordResetInput,
    LoginUserInput,
    PasswordResetRequestedDTO,
    ProfileDTO,
    RefreshTokenInput,
    RegisterUserInput,
    RequestPasswordResetInput,
    SocialLoginInput,
    UpdateProfileInput,
    UserDTO,
)
from accounts.application.ports import (
    AuthTokenService,
    PasswordHasher,
    PasswordResetGateway,
    ProfileRepository,
    SocialIdentityProvider,
    TokenPair,
    UserRepository,
)
from accounts.domain.entities import Profile, User
from accounts.domain.exceptions import (
    EmailAlreadyTakenError,
    InvalidCredentialsError,
    PasswordResetTokenInvalidError,
    ProfileNotFoundError,
    UserNotFoundError,
)
from accounts.domain.value_objects import Email
from shared.application.patch import apply_patch
from shared.application.ports import UnitOfWork
from shared.domain.currency_code import CurrencyCode


def _user_dto(user: User) -> UserDTO:
    return UserDTO(id=user.id, email=user.email.value, first_name=user.first_name)


def _profile_dto(profile: Profile) -> ProfileDTO:
    return ProfileDTO(
        user_id=profile.user_id,
        base_currency=profile.base_currency.value,
        theme=profile.theme,
        onboarded=profile.onboarded,
        notify_budget=profile.notify_budget,
        notify_goal=profile.notify_goal,
        notify_recurring=profile.notify_recurring,
        notify_weekly_report=profile.notify_weekly_report,
    )


class RegisterUser:
    def __init__(
        self,
        user_repo: UserRepository,
        profile_repo: ProfileRepository,
        password_hasher: PasswordHasher,
        token_service: AuthTokenService,
        uow: UnitOfWork,
    ) -> None:
        self._users = user_repo
        self._profiles = profile_repo
        self._hasher = password_hasher
        self._tokens = token_service
        self._uow = uow

    def execute(self, data: RegisterUserInput) -> AuthResultDTO:
        email = Email(data.email)
        if self._users.email_exists(email):
            raise EmailAlreadyTakenError
        password_hash = self._hasher.hash(data.password)
        with self._uow:
            # UserRepository.add raises EmailAlreadyTakenError if a concurrent
            # registration wins the race past the check above.
            user = self._users.add(User(email=email, first_name=data.first_name), password_hash)
            self._profiles.add(Profile(user_id=user.id))
        return AuthResultDTO(user=_user_dto(user), tokens=self._tokens.issue(user))


class LoginUser:
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        token_service: AuthTokenService,
    ) -> None:
        self._users = user_repo
        self._hasher = password_hasher
        self._tokens = token_service

    def execute(self, data: LoginUserInput) -> AuthResultDTO:
        email = Email(data.email)
        user = self._users.get_by_email(email)
        if user is None:
            # Hash anyway so response time does not reveal whether the email exists.
            self._hasher.hash(data.password)
            raise InvalidCredentialsError
        password_hash = self._users.get_password_hash(user.id)
        if not self._hasher.verify(data.password, password_hash or ""):
            raise InvalidCredentialsError
        return AuthResultDTO(user=_user_dto(user), tokens=self._tokens.issue(user))


class RefreshToken:
    def __init__(self, token_service: AuthTokenService) -> None:
        self._tokens = token_service

    def execute(self, data: RefreshTokenInput) -> TokenPair:
        return self._tokens.refresh(data.refresh_token)


class LogoutUser:
    def __init__(self, token_service: AuthTokenService) -> None:
        self._tokens = token_service

    def execute(self, data: RefreshTokenInput) -> None:
        self._tokens.revoke(data.refresh_token)


class SocialLogin:
    def __init__(
        self,
        provider: SocialIdentityProvider,
        user_repo: UserRepository,
        profile_repo: ProfileRepository,
        password_hasher: PasswordHasher,
        token_service: AuthTokenService,
        uow: UnitOfWork,
    ) -> None:
        self._provider = provider
        self._users = user_repo
        self._profiles = profile_repo
        self._hasher = password_hasher
        self._tokens = token_service
        self._uow = uow

    def execute(self, data: SocialLoginInput) -> AuthResultDTO:
        identity = self._provider.exchange(data.provider, data.credential)
        if identity is None:
            raise InvalidCredentialsError
        user = self._users.get_by_email(identity.email)
        if user is None:
            # Social users have no password — store an unusable random hash.
            password_hash = self._hasher.hash(secrets.token_urlsafe(48))
            with self._uow:
                user = self._users.add(
                    User(email=identity.email, first_name=identity.first_name), password_hash
                )
                self._profiles.add(Profile(user_id=user.id))
        return AuthResultDTO(user=_user_dto(user), tokens=self._tokens.issue(user))


class GetProfile:
    def __init__(self, profile_repo: ProfileRepository) -> None:
        self._profiles = profile_repo

    def execute(self, user_id: UUID) -> ProfileDTO:
        profile = self._profiles.get_by_user(user_id)
        if profile is None:
            raise ProfileNotFoundError(user_id)
        return _profile_dto(profile)


class UpdateProfile:
    def __init__(self, profile_repo: ProfileRepository) -> None:
        self._profiles = profile_repo

    def execute(self, user_id: UUID, data: UpdateProfileInput) -> ProfileDTO:
        profile = self._profiles.get_by_user(user_id)
        if profile is None:
            raise ProfileNotFoundError(user_id)
        updated = apply_patch(
            profile, data, fields={"base_currency": ("base_currency", CurrencyCode)}
        )
        return _profile_dto(self._profiles.update(updated))


class ChangePassword:
    def __init__(self, user_repo: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = user_repo
        self._hasher = password_hasher

    def execute(self, user_id: UUID, data: ChangePasswordInput) -> None:
        user = self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        current_hash = self._users.get_password_hash(user_id)
        if not self._hasher.verify(data.old_password, current_hash or ""):
            raise InvalidCredentialsError
        self._users.set_password(user_id, self._hasher.hash(data.new_password))


class RequestPasswordReset:
    def __init__(self, user_repo: UserRepository, reset_gateway: PasswordResetGateway) -> None:
        self._users = user_repo
        self._gateway = reset_gateway

    def execute(self, data: RequestPasswordResetInput) -> PasswordResetRequestedDTO:
        # Always acknowledge to avoid leaking which emails are registered.
        user = self._users.get_by_email(Email(data.email))
        if user is not None:
            token = self._gateway.issue_token(user)
            # The gateway implementation is responsible for delivering the token.
            del token
        return PasswordResetRequestedDTO(acknowledged=True)


class ConfirmPasswordReset:
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        reset_gateway: PasswordResetGateway,
    ) -> None:
        self._users = user_repo
        self._hasher = password_hasher
        self._gateway = reset_gateway

    def execute(self, data: ConfirmPasswordResetInput) -> None:
        user_id = self._gateway.resolve_token(data.token)
        if user_id is None:
            raise PasswordResetTokenInvalidError
        user = self._users.get_by_id(user_id)
        if user is None:
            raise PasswordResetTokenInvalidError
        self._users.set_password(user_id, self._hasher.hash(data.new_password))
        self._gateway.invalidate_token(data.token)
