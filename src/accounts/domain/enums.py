"""Enums for the accounts bounded context."""

from enum import StrEnum


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class CodePurpose(StrEnum):
    """What a mailed one-time code confirms."""

    VERIFY_EMAIL = "verify_email"
    CHANGE_PASSWORD = "change_password"
    RESET_PASSWORD = "reset_password"
