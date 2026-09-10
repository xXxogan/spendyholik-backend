"""ISO 4217 currency code value object."""

from __future__ import annotations

from dataclasses import dataclass

from shared.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class CurrencyCode:
    """A three-letter ISO 4217 currency code, normalised to uppercase."""

    value: str

    def __post_init__(self) -> None:
        value = self.value.upper()
        if len(value) != 3 or not value.isalpha():
            msg = f"Invalid ISO 4217 currency code: {self.value!r}"
            raise ValidationError(msg)
        object.__setattr__(self, "value", value)

    def __str__(self) -> str:
        return self.value
