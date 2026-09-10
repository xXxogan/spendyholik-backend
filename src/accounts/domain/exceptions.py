"""Domain exceptions for the accounts bounded context."""

from __future__ import annotations

from shared.exceptions import BusinessRuleError, EntityNotFoundError, ValidationError


class EmailAlreadyTakenError(BusinessRuleError):
    code = "email_already_taken"
    default_detail = "A user with this email already exists."


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
