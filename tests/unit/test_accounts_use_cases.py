from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from accounts.application.dto import (
    ChangePasswordInput,
    ConfirmEmailInput,
    ConfirmPasswordResetInput,
    LoginUserInput,
    RegisterUserInput,
    RequestPasswordResetInput,
    SocialLoginInput,
    UpdateProfileInput,
)
from accounts.application.ports import SocialIdentity
from accounts.application.use_cases import (
    ChangePassword,
    ConfirmEmail,
    ConfirmPasswordReset,
    GetProfile,
    LoginUser,
    RegisterUser,
    RequestPasswordChangeCode,
    RequestPasswordReset,
    ResendEmailCode,
    SocialLogin,
    UpdateProfile,
)
from accounts.domain.enums import CodePurpose
from accounts.domain.exceptions import (
    EmailAlreadyTakenError,
    EmailAlreadyVerifiedError,
    InvalidCodeError,
    InvalidCredentialsError,
    ProfileNotFoundError,
    ResendTooSoonError,
    WrongPasswordError,
)
from accounts.domain.value_objects import Email
from shared.exceptions import ValidationError as DomainValidationError
from tests.fakes import (
    FakeAuthTokenService,
    FakeClock,
    FakePasswordHasher,
    FakeSocialIdentityProvider,
    FakeUnitOfWork,
    InMemoryProfileRepository,
    InMemoryUserRepository,
    fake_codes,
)

CODES, SENDER, REPO = None, None, None


def _past_cooldown():
    """Forget the live codes, as if the resend cooldown had passed."""
    REPO.by_key.clear()


def _registrar():
    global CODES, SENDER, REPO
    CODES, SENDER, REPO = fake_codes()
    users = InMemoryUserRepository()
    profiles = InMemoryProfileRepository()
    hasher = FakePasswordHasher()
    tokens = FakeAuthTokenService()
    return users, profiles, hasher, tokens


def _register(users, profiles, hasher, tokens, email="a@b.co", password="password123"):
    return RegisterUser(
        users, profiles, hasher, tokens, FakeUnitOfWork(), FakeClock(), CODES
    ).execute(
        RegisterUserInput(
            email=email, password=password, first_name="Ann", personal_data_consent=True
        )
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
            RegisterUser(
                users, profiles, hasher, tokens, FakeUnitOfWork(), FakeClock(), CODES
            ).execute(
                RegisterUserInput(email="nope", password="password123", personal_data_consent=True)
            )

    def test_short_password_rejected_by_input_dto(self):
        with pytest.raises(PydanticValidationError):
            RegisterUserInput(email="a@b.co", password="short", personal_data_consent=True)


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
        profile = GetProfile(profiles, users).execute(result.user.id)
        assert profile.base_currency == "RUB"
        assert profile.email == "a@b.co"

    def test_get_profile_missing_raises(self):
        with pytest.raises(ProfileNotFoundError):
            GetProfile(InMemoryProfileRepository(), InMemoryUserRepository()).execute(uuid4())

    def test_update_profile(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        updated = UpdateProfile(profiles, users, FakeUnitOfWork(), CODES, hasher, SENDER).execute(
            result.user.id, UpdateProfileInput(onboarded=True, theme="dark")
        )
        assert updated.onboarded is True
        assert updated.theme.value == "dark"

    def test_update_name_and_email(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        _past_cooldown()
        updated = UpdateProfile(profiles, users, FakeUnitOfWork(), CODES, hasher, SENDER).execute(
            result.user.id,
            UpdateProfileInput(first_name="Аня", email="New@B.co", current_password="password123"),
        )
        assert (updated.first_name, updated.email) == ("Аня", "new@b.co")
        assert users.get_by_id(result.user.id).email.value == "new@b.co"
        LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="new@b.co", password="password123")
        )

    def test_update_to_a_taken_email_rejected(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        RegisterUser(users, profiles, hasher, tokens, FakeUnitOfWork(), FakeClock(), CODES).execute(
            RegisterUserInput(
                email="taken@b.co", password="password123", personal_data_consent=True
            )
        )
        with pytest.raises(EmailAlreadyTakenError) as exc:
            UpdateProfile(profiles, users, FakeUnitOfWork(), CODES, hasher, SENDER).execute(
                result.user.id,
                UpdateProfileInput(email="taken@b.co", current_password="password123"),
            )
        assert exc.value.errors == {"email": "email_already_taken"}


class TestChangePassword:
    def _change(self, users, hasher, tokens, user_id, code, new="newpass456"):
        ChangePassword(users, hasher, tokens, CODES).execute(
            user_id, ChangePasswordInput(code=code, new_password=new)
        )

    def test_changes_password_with_the_mailed_code(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        RequestPasswordChangeCode(users, CODES).execute(result.user.id)
        assert SENDER.sent[-1][1] is CodePurpose.CHANGE_PASSWORD
        self._change(users, hasher, tokens, result.user.id, SENDER.last_code)
        LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="a@b.co", password="newpass456")
        )

    def test_wrong_code_raises_and_password_stays(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        RequestPasswordChangeCode(users, CODES).execute(result.user.id)
        with pytest.raises(InvalidCodeError) as exc:
            self._change(users, hasher, tokens, result.user.id, "000000x")
        assert exc.value.errors == {"code": "invalid_code"}
        LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="a@b.co", password="password123")
        )

    def test_code_without_request_is_invalid(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        with pytest.raises(InvalidCodeError):
            self._change(users, hasher, tokens, result.user.id, "123456")


class TestEmailConfirmation:
    def test_registration_mails_a_code_and_leaves_email_unconfirmed(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        assert result.user.email_verified is False
        assert SENDER.sent[-1][:2] == ("a@b.co", CodePurpose.VERIFY_EMAIL)
        confirmed = ConfirmEmail(users, CODES).execute(
            result.user.id, ConfirmEmailInput(code=SENDER.last_code)
        )
        assert confirmed.email_verified is True
        with pytest.raises(InvalidCodeError):  # a used code is gone
            CODES.verify(result.user.id, CodePurpose.VERIFY_EMAIL, SENDER.last_code)

    def test_already_confirmed(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        ConfirmEmail(users, CODES).execute(result.user.id, ConfirmEmailInput(code=SENDER.last_code))
        with pytest.raises(EmailAlreadyVerifiedError):
            ResendEmailCode(users, CODES).execute(result.user.id)

    def test_changing_the_email_needs_a_new_confirmation(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        ConfirmEmail(users, CODES).execute(result.user.id, ConfirmEmailInput(code=SENDER.last_code))
        updated = UpdateProfile(profiles, users, FakeUnitOfWork(), CODES, hasher, SENDER).execute(
            result.user.id, UpdateProfileInput(email="new@b.co", current_password="password123")
        )
        assert updated.email_verified is False
        assert SENDER.sent[-2][:2] == ("new@b.co", CodePurpose.VERIFY_EMAIL)
        assert SENDER.sent[-1] == ("a@b.co", "email_changed", "new@b.co")

    def _move(self, users, profiles, hasher, user_id, **fields):
        return UpdateProfile(profiles, users, FakeUnitOfWork(), CODES, hasher, SENDER).execute(
            user_id, UpdateProfileInput(email="new@b.co", **fields)
        )

    def test_changing_the_email_needs_the_current_password(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        _past_cooldown()
        with pytest.raises(DomainValidationError) as exc:
            self._move(users, profiles, hasher, result.user.id)
        assert exc.value.errors == {"current_password": "required"}
        with pytest.raises(WrongPasswordError) as exc:
            self._move(users, profiles, hasher, result.user.id, current_password="nope")
        assert exc.value.errors == {"current_password": "wrong_password"}
        assert users.get_by_id(result.user.id).email.value == "a@b.co"

    def test_email_change_respects_the_resend_cooldown(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        with pytest.raises(ResendTooSoonError):
            self._move(users, profiles, hasher, result.user.id, current_password="password123")

    def test_email_change_revokes_a_pending_password_code(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        ConfirmEmail(users, CODES).execute(result.user.id, ConfirmEmailInput(code=SENDER.last_code))
        RequestPasswordChangeCode(users, CODES).execute(result.user.id)
        old_code = SENDER.last_code
        self._move(users, profiles, hasher, result.user.id, current_password="password123")
        with pytest.raises(InvalidCodeError):
            CODES.verify(result.user.id, CodePurpose.CHANGE_PASSWORD, old_code)


class TestPasswordReset:
    def _reset(self, users, hasher, tokens, code, email="a@b.co"):
        ConfirmPasswordReset(users, hasher, tokens, CODES).execute(
            ConfirmPasswordResetInput(email=email, code=code, new_password="newpass456")
        )

    def test_request_and_confirm_with_the_mailed_code(self):
        users, profiles, hasher, tokens = _registrar()
        result = _register(users, profiles, hasher, tokens)
        requested = RequestPasswordReset(users, CODES).execute(
            RequestPasswordResetInput(email="A@b.co")
        )
        assert requested.acknowledged is True
        email, purpose, code = SENDER.sent[-1]
        assert (email, purpose, len(code)) == ("a@b.co", CodePurpose.RESET_PASSWORD, 6)
        self._reset(users, hasher, tokens, code)
        LoginUser(users, hasher, tokens).execute(
            LoginUserInput(email="a@b.co", password="newpass456")
        )
        # The code reached the mailbox, so the address is confirmed too.
        assert users.get_by_id(result.user.id).email_verified is True

    def test_wrong_code_raises(self):
        users, profiles, hasher, tokens = _registrar()
        _register(users, profiles, hasher, tokens)
        RequestPasswordReset(users, CODES).execute(RequestPasswordResetInput(email="a@b.co"))
        with pytest.raises(InvalidCodeError):
            self._reset(users, hasher, tokens, "000000x")

    def test_unknown_email_looks_like_a_wrong_code(self):
        users, profiles, hasher, tokens = _registrar()
        with pytest.raises(InvalidCodeError):
            self._reset(users, hasher, tokens, "123456", email="nobody@b.co")
        with pytest.raises(InvalidCodeError):
            self._reset(users, hasher, tokens, "123456", email="not-an-email")

    def test_request_answers_the_same_for_any_email(self):
        users, profiles, hasher, tokens = _registrar()
        _register(users, profiles, hasher, tokens)
        request = RequestPasswordReset(users, CODES)
        sent_before = len(SENDER.sent)
        assert request.execute(RequestPasswordResetInput(email="nobody@b.co")).acknowledged
        assert request.execute(RequestPasswordResetInput(email="broken")).acknowledged
        assert len(SENDER.sent) == sent_before
        request.execute(RequestPasswordResetInput(email="a@b.co"))
        # Within the cooldown: still "acknowledged", no error that would reveal the account.
        assert request.execute(RequestPasswordResetInput(email="a@b.co")).acknowledged


class TestSocialLogin:
    def test_creates_user_on_first_login(self):
        users = InMemoryUserRepository()
        profiles = InMemoryProfileRepository()
        hasher = FakePasswordHasher()
        tokens = FakeAuthTokenService()
        provider = FakeSocialIdentityProvider(
            {"google:code123": SocialIdentity("google", Email("g@b.co"), "G")}
        )
        result = SocialLogin(provider, users, profiles, hasher, tokens, FakeUnitOfWork()).execute(
            SocialLoginInput(provider="google", credential="code123")
        )
        assert result.user.email == "g@b.co"
        assert profiles.get_by_user(result.user.id) is not None

    def test_unknown_credential_raises(self):
        users = InMemoryUserRepository()
        profiles = InMemoryProfileRepository()
        provider = FakeSocialIdentityProvider()
        with pytest.raises(InvalidCredentialsError):
            SocialLogin(
                provider,
                users,
                profiles,
                FakePasswordHasher(),
                FakeAuthTokenService(),
                FakeUnitOfWork(),
            ).execute(SocialLoginInput(provider="google", credential="bad"))
