"""Domain exceptions for the accounts bounded context."""

from __future__ import annotations

from shared.exceptions import BusinessRuleError, EntityNotFoundError, ValidationError


class EmailAlreadyTakenError(BusinessRuleError):
    code = "email_already_taken"
    default_detail = "A user with this email already exists."
    field = "email"


class InvalidCredentialsError(ValidationError):
    code = "invalid_credentials"
    http_status = 401
    default_detail = "Invalid email or password."


class UserNotFoundError(EntityNotFoundError):
    code = "user_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("User", identifier)


class ProfileNotFoundError(EntityNotFoundError):
    code = "profile_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Profile", identifier)


class InvalidTokenError(ValidationError):
    code = "token_invalid"
    http_status = 401
    default_detail = "The token is invalid or expired."


class WrongPasswordError(ValidationError):
    """The current password given to confirm a change is wrong (422, not 401:
    the session itself is valid)."""

    code = "wrong_password"
    default_detail = "The current password is wrong."
    field = "current_password"


class EmailNotVerifiedError(BusinessRuleError):
    """The account's email is not confirmed yet; data endpoints stay closed."""

    code = "email_not_verified"
    http_status = 403
    default_detail = "Confirm your email with the code we sent."


class EmailAlreadyVerifiedError(BusinessRuleError):
    code = "email_already_verified"
    default_detail = "The email is already confirmed."


class InvalidCodeError(ValidationError):
    code = "invalid_code"
    default_detail = "The code is wrong."
    field = "code"


class CodeExpiredError(ValidationError):
    code = "code_expired"
    default_detail = "The code has expired; request a new one."
    field = "code"


class TooManyAttemptsError(ValidationError):
    code = "too_many_attempts"
    http_status = 429
    default_detail = "Too many wrong codes; request a new one."
    field = "code"


class TooManyCodesError(BusinessRuleError):
    code = "too_many_codes"
    http_status = 429
    default_detail = "Too many codes today; try again tomorrow."


class ResendTooSoonError(BusinessRuleError):
    code = "resend_too_soon"
    http_status = 429
    default_detail = "A code was sent recently; wait before asking again."

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"A code was sent recently; try again in {retry_after} s.")
