"""Conversion of multi-currency totals into the user's base currency."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from accounts.application.ports import ProfileRepository
from finances.application.ports import CurrencyTotals, ExchangeRateRepository
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import DEFAULT_CURRENCY, Money


def base_currency_for(profiles: ProfileRepository, user_id: UUID) -> str:
    profile = profiles.get_by_user(user_id)
    return profile.base_currency.value if profile else DEFAULT_CURRENCY


#: Currencies a missing direct rate is triangulated through (the provider's base).
PIVOT_CURRENCIES = ("USD",)


class CurrencyConverter:
    """Converts per-currency totals into one base currency.

    A rate is taken directly, inverted, or crossed through a pivot currency
    (rates are fetched against USD, so RUB→EUR is RUB→USD→EUR). Currencies
    without any rate are skipped and collected in :attr:`excluded`, so a
    missing rate degrades the totals instead of failing the whole request.
    """

    def __init__(
        self,
        rates: ExchangeRateRepository,
        base: str,
        pivots: tuple[str, ...] = PIVOT_CURRENCIES,
    ) -> None:
        self._rates = rates
        self.base = base
        self._pivots = pivots
        self.excluded: set[str] = set()
        self._cache: dict[str, Decimal | None] = {base: Decimal(1)}

    def _pair(self, source: str, target: str) -> Decimal | None:
        """Units of ``target`` per 1 ``source`` from a stored or inverted rate."""
        if source == target:
            return Decimal(1)
        src, dst = CurrencyCode(source), CurrencyCode(target)
        direct = self._rates.get_latest(src, dst)
        if direct is not None:
            return direct.rate
        inverse = self._rates.get_latest(dst, src)
        return Decimal(1) / inverse.rate if inverse else None

    def _rate(self, currency: str) -> Decimal | None:
        if currency not in self._cache:
            rate = self._pair(currency, self.base)
            for pivot in self._pivots:
                if rate is not None:
                    break
                to_pivot = self._pair(currency, pivot)
                from_pivot = self._pair(pivot, self.base) if to_pivot is not None else None
                if to_pivot is not None and from_pivot is not None:
                    rate = to_pivot * from_pivot
            self._cache[currency] = rate
        return self._cache[currency]

    def can_convert(self, currency: str) -> bool:
        return self._rate(currency) is not None

    def total(self, totals: CurrencyTotals | None) -> Money:
        result = Money.zero(self.base)
        for currency, money in (totals or {}).items():
            rate = self._rate(currency)
            if rate is None:
                self.excluded.add(currency)
                continue
            result = result + Money(money.amount * rate, self.base)
        return result

    def sum(self, items: Iterable[Money]) -> Money:
        totals: CurrencyTotals = {}
        for money in items:
            totals[money.currency] = totals.get(money.currency, Money.zero(money.currency)) + money
        return self.total(totals)
