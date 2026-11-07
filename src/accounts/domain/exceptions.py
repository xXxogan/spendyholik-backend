"""Domain exceptions for the accounts bounded context."""

from __future__ import annotations

from shared.exceptions import BusinessRuleError, EntityNotFoundError, ValidationError


class EmailAlreadyTakenError(BusinessRuleError):
    code = "email_already_taken"
    default_detail = "A user with this email already exists."
    field = "email"


class WrongPasswordError(ValidationError):
    """The current password given to confirm a change is wrong (422, not 401:
    the session itself is valid)."""

    code = "wrong_password"
    default_detail = "The current password is wrong."
    field = "old_password"


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


class PasswordResetTokenInvalidError(ValidationError):
    code = "password_reset_token_invalid"
    default_detail = "The password reset token is invalid or expired."


class InvalidTokenError(ValidationError):
    code = "token_invalid"
    http_status = 401
    default_detail = "The token is invalid or expired."
