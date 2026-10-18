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


class CurrencyConverter:
    """Converts per-currency totals into one base currency.

    Currencies without a known exchange rate are skipped and collected in
    :attr:`excluded`, so a missing rate degrades the totals instead of failing
    the whole request.
    """

    def __init__(self, rates: ExchangeRateRepository, base: str) -> None:
        self._rates = rates
        self.base = base
        self.excluded: set[str] = set()
        self._cache: dict[str, Decimal | None] = {base: Decimal(1)}

    def _rate(self, currency: str) -> Decimal | None:
        if currency not in self._cache:
            source, target = CurrencyCode(currency), CurrencyCode(self.base)
            direct = self._rates.get_latest(source, target)
            if direct is not None:
                self._cache[currency] = direct.rate
            else:
                inverse = self._rates.get_latest(target, source)
                self._cache[currency] = Decimal(1) / inverse.rate if inverse else None
        return self._cache[currency]

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
