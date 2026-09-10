"""Enums for the accounts bounded context."""

from enum import StrEnum


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"
