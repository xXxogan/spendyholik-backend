from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from accounts.application.dto import (
    ChangePasswordInput,
    ConfirmPasswordResetInput,
    LoginUserInput,
    RegisterUserInput,
    RequestPasswordResetInput,
    SocialLoginInput,
    UpdateProfileInput,
)
from accounts.application.ports import SocialIdentity
from accounts.domain.value_objects import Email
from accounts.application.use_cases import (
    ChangePassword,
    ConfirmPasswordReset,
    GetProfile,
    LoginUser,
    RegisterUser,
    RequestPasswordReset,
    SocialLogin,
    UpdateProfile,
)
from accounts.domain.exceptions import (
    EmailAlreadyTakenError,
    InvalidCredentialsError,
    PasswordResetTokenInvalidError,
    ProfileNotFoundError,
)
from shared.exceptions import ValidationError as DomainValidationError
from tests.fakes import (
    FakeAuthTokenService,
    FakePasswordHasher,
    FakePasswordResetGateway,
    FakeSocialIdentityProvider,
    InMemoryProfileRepository,
    InMemoryUserRepository,
)


def _registrar():
    users = InMemoryUserRepository()
    profiles = InMemoryProfileRepository()
    hasher = FakePasswordHasher()
    tokens = FakeAuthTokenService()
    return users, profiles, hasher, tokens


def _register(users, profiles, hasher, tokens, email="a@b.co", password="password123"):
    return RegisterUser(users, profiles, hasher, tokens).execute(
        RegisterUserInput(email=email, password=password, first_name="Ann")
    )


class TestRegisterUser:
    def test_registers_user_and_profile_and_returns_tokens(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        assert result.user.email == "a@b.co"
        assert result.tokens.access.startswith("access-")
        assert profiles.get_by_user(result.user.id) is not None

    def test_duplicate_email_raises(self):
        users, profiles, hasher, tokens = _registrar()
        _register(users, profiles, hasher, tokens)
        with pytest.raises(EmailAlreadyTakenError):
            _register(users, profiles, hasher, tokens)

    def test_invalid_email_raises(self):
        users, profiles, hasher, tokens = _registrar()
        with pytest.raises(DomainValidationError):
            RegisterUser(users, profiles, hasher, tokens).execute(
                RegisterUserInput(email="nope", password="password123")
            )

    def test_short_password_rejected_by_input_dto(self):
        with pytest.raises(PydanticValidationError):
            RegisterUserInput(email="a@b.co", password="short")


class TestLoginUser:
    def test_login_success(self):
        users, profiles, hasher, tokens = _registrar()
        _register(users, profiles, hasher, tokens)
        result = LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="a@b.co", password="password123")
        )
        assert result.tokens.refresh.startswith("refresh-")

    def test_wrong_password_raises(self):
        users, profiles, hasher, tokens = _registrar()
        _register(users, profiles, hasher, tokens)
        with pytest.raises(InvalidCredentialsError):
            LoginUser(users, hasher, tokens).execute(
                LoginUserInput(email="a@b.co", password="wrong")
            )

    def test_unknown_email_raises(self):
        users, profiles, hasher, tokens = _registrar()
        with pytest.raises(InvalidCredentialsError):
            LoginUser(users, hasher, tokens).execute(
                LoginUserInput(email="x@y.co", password="password123")
            )


class TestProfile:
    def test_get_profile(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        profile = GetProfile(profiles).execute(result.user.id)
        assert profile.base_currency == "RUB"

    def test_get_profile_missing_raises(self):
        with pytest.raises(ProfileNotFoundError):
            GetProfile(InMemoryProfileRepository()).execute(uuid4())

    def test_update_profile(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        updated = UpdateProfile(profiles).execute(
            result.user.id, UpdateProfileInput(onboarded=True, theme="dark")
        )
        assert updated.onboarded is True
        assert updated.theme.value == "dark"


class TestChangePassword:
    def test_changes_password(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        ChangePassword(users, hasher).execute(
            result.user.id, ChangePasswordInput(old_password="password123", new_password="newpass456")
        )
        # Login with the new password succeeds.
        LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="a@b.co", password="newpass456")
        )

    def test_wrong_old_password_raises(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        with pytest.raises(InvalidCredentialsError):
            ChangePassword(users, hasher).execute(
                result.user.id, ChangePasswordInput(old_password="bad", new_password="newpass456")
            )


class TestPasswordReset:
    def test_request_and_confirm(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        gateway = FakePasswordResetGateway()
        requested = RequestPasswordReset(users, gateway).execute(
            RequestPasswordResetInput(email="a@b.co")
        )
        assert requested.acknowledged is True
        token = next(iter(gateway._tokens))
        ConfirmPasswordReset(users, hasher, gateway).execute(
            ConfirmPasswordResetInput(token=token, new_password="newpass456")
        )
        LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="a@b.co", password="newpass456")
        )

    def test_confirm_with_bad_token_raises(self):
        users, profiles, hasher, tokens = _registrar()
        _register(users, profiles, hasher, tokens)
        gateway = FakePasswordResetGateway()
        with pytest.raises(PasswordResetTokenInvalidError):
            ConfirmPasswordReset(users, hasher, gateway).execute(
                ConfirmPasswordResetInput(token="bogus", new_password="newpass456")
            )


class TestSocialLogin:
    def test_creates_user_on_first_login(self):
        users = InMemoryUserRepository()
        profiles = InMemoryProfileRepository()
        hasher = FakePasswordHasher()
        tokens = FakeAuthTokenService()
        provider = FakeSocialIdentityProvider(
            {"google:code123": SocialIdentity("google", Email("g@b.co"), "G")}
        )
        result = SocialLogin(provider, users, profiles, hasher, tokens).execute(
            SocialLoginInput(provider="google", credential="code123")
        )
        assert result.user.email == "g@b.co"
        assert profiles.get_by_user(result.user.id) is not None

    def test_unknown_credential_raises(self):
        users = InMemoryUserRepository()
        profiles = InMemoryProfileRepository()
        provider = FakeSocialIdentityProvider()
        with pytest.raises(InvalidCredentialsError):
            SocialLogin(provider, users, profiles, FakePasswordHasher(), FakeAuthTokenService()).execute(
                SocialLoginInput(provider="google", credential="bad")
            )
