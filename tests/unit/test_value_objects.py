from datetime import date

import pytest

from shared.domain.currency_code import CurrencyCode
from shared.domain.date_range import DateRange
from shared.exceptions import ValidationError


class TestDateRange:
    def test_valid_range(self):
        r = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 31))
        assert r.days == 31
        assert r.contains(date(2026, 1, 15)) is True
        assert r.contains(date(2026, 2, 1)) is False

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError):
            DateRange(start=date(2026, 2, 1), end=date(2026, 1, 1))

    def test_equal_ranges(self):
        assert DateRange(date(2026, 1, 1), date(2026, 1, 2)) == DateRange(
            date(2026, 1, 1), date(2026, 1, 2)
        )


class TestCurrencyCode:
    def test_creates_valid_code(self):
        assert str(CurrencyCode("usd")) == "USD"

    def test_uppercases(self):
        assert CurrencyCode("rub").value == "RUB"

    def test_rejects_non_three_letter(self):
        with pytest.raises(ValidationError):
            CurrencyCode("US")

    def test_rejects_non_alpha(self):
        with pytest.raises(ValidationError):
            CurrencyCode("US1")

    def test_equality(self):
        assert CurrencyCode("USD") == CurrencyCode("usd")
