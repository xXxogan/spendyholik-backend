"""Money value object — exact decimal amount with an ISO 4217 currency."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from shared.domain.currency_code import CurrencyCode
from shared.exceptions import CurrencyMismatchError

#: The number of decimal places stored for monetary values (minor units = 10**2).
DECIMAL_PLACES = 2
MINOR_UNIT_FACTOR = Decimal(10) ** DECIMAL_PLACES
_QUANTUM = Decimal("0.01")

#: Default base currency for new users/profiles.
DEFAULT_CURRENCY = "RUB"


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable amount of money in a specific currency.

    ``amount`` is an exact ``Decimal`` with two decimal places; ``currency``
    is normalised to an uppercase ISO 4217 code. Operations between different
    currencies raise :class:`CurrencyMismatchError`.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", CurrencyCode(self.currency).value)
        object.__setattr__(self, "amount", self.amount.quantize(_QUANTUM, rounding=ROUND_HALF_UP))

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------
    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal("0.00"), currency)

    @classmethod
    def from_minor_units(cls, minor_units: int, currency: str) -> Money:
        return cls(Decimal(minor_units) / MINOR_UNIT_FACTOR, currency)

    def to_minor_units(self) -> int:
        """Return the amount in minor units (kopecks/cents) as an integer."""
        return int((self.amount * MINOR_UNIT_FACTOR).to_integral_value(rounding=ROUND_HALF_UP))

    # ------------------------------------------------------------------
    # Predicates
    # ------------------------------------------------------------------
    def is_negative(self) -> bool:
        return self.amount < 0

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_positive(self) -> bool:
        return self.amount > 0

    # ------------------------------------------------------------------
    # Arithmetic
    # ------------------------------------------------------------------
    def _ensure_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __mul__(self, scalar: object) -> Money:
        if isinstance(scalar, Money):
            raise TypeError("Cannot multiply two Money values.")
        return Money(self.amount * Decimal(str(scalar)), self.currency)

    __rmul__ = __mul__

    def __truediv__(self, scalar: object) -> Money:
        if isinstance(scalar, Money):
            raise TypeError("Cannot divide Money by Money.")
        return Money(self.amount / Decimal(str(scalar)), self.currency)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return self.amount >= other.amount
