"""Value objects for the accounts bounded context."""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.exceptions import ValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class Email:
    """A normalised email address."""

    value: str

    def __post_init__(self) -> None:
        value = self.value.strip().lower()
        if not _EMAIL_RE.match(value):
            msg = f"Invalid email address: {self.value!r}"
            raise ValidationError(msg)
        object.__setattr__(self, "value", value)

    def __str__(self) -> str:
        return self.value
