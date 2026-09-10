"""Enums for the debts bounded context."""

from enum import StrEnum


class DebtDirection(StrEnum):
    I_OWE = "i_owe"
    OWED_TO_ME = "owed_to_me"
