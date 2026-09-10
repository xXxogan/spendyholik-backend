"""Value objects for the finances bounded context."""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.exceptions import ValidationError

_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class CategoryColor:
    """A semantic color token (e.g. ``cat-food``)."""

    value: str

    def __post_init__(self) -> None:
        value = self.value.strip().lower()
        if not _TOKEN_RE.match(value):
            msg = f"Invalid category color token: {self.value!r}"
            raise ValidationError(msg)
        object.__setattr__(self, "value", value)

    def __str__(self) -> str:
        return self.value
