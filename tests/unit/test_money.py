from decimal import Decimal

import pytest

from shared.domain.money import Money
from shared.exceptions import CurrencyMismatchError, DomainError


class TestMoneyConstruction:
    def test_creates_from_decimal_and_normalizes_currency(self):
        money = Money(Decimal("12.34"), "rub")
        assert money.amount == Decimal("12.34")
        assert money.currency == "RUB"

    def test_equal_amounts_and_currency_are_equal(self):
        assert Money(Decimal("1.00"), "USD") == Money(Decimal("1.00"), "usd")

    def test_quantizes_amount_to_two_decimal_places(self):
        assert Money(Decimal("1.005"), "RUB").amount == Decimal("1.01")

    def test_zero_classmethod(self):
        assert Money.zero("RUB") == Money(Decimal("0.00"), "RUB")

    def test_from_minor_units(self):
        assert Money.from_minor_units(1240, "RUB") == Money(Decimal("12.40"), "RUB")

    def test_from_minor_units_negative(self):
        assert Money.from_minor_units(-50, "RUB") == Money(Decimal("-0.50"), "RUB")


class TestMoneyArithmetic:
    def test_add_same_currency(self):
        result = Money(Decimal("1.50"), "RUB") + Money(Decimal("2.25"), "RUB")
        assert result == Money(Decimal("3.75"), "RUB")

    def test_add_different_currency_raises(self):
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal("1.00"), "RUB") + Money(Decimal("1.00"), "USD")

    def test_sub_same_currency(self):
        result = Money(Decimal("10.00"), "RUB") - Money(Decimal("3.25"), "RUB")
        assert result == Money(Decimal("6.75"), "RUB")

    def test_sub_different_currency_raises(self):
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal("10.00"), "RUB") - Money(Decimal("1.00"), "EUR")

    def test_neg(self):
        assert -Money(Decimal("5.00"), "RUB") == Money(Decimal("-5.00"), "RUB")

    def test_mul_by_scalar(self):
        assert Money(Decimal("2.00"), "RUB") * 3 == Money(Decimal("6.00"), "RUB")

    def test_truediv_by_scalar(self):
        assert Money(Decimal("6.00"), "RUB") / 3 == Money(Decimal("2.00"), "RUB")

    def test_is_negative(self):
        assert Money(Decimal("-1.00"), "RUB").is_negative() is True
        assert Money(Decimal("0.00"), "RUB").is_negative() is False
        assert Money(Decimal("1.00"), "RUB").is_negative() is False

    def test_is_zero_and_positive(self):
        assert Money(Decimal("0.00"), "RUB").is_zero() is True
        assert Money(Decimal("1.00"), "RUB").is_positive() is True


class TestMoneyComparison:
    def test_lt_same_currency(self):
        assert Money(Decimal("1.00"), "RUB") < Money(Decimal("2.00"), "RUB")

    def test_lt_different_currency_raises(self):
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal("1.00"), "RUB") < Money(Decimal("2.00"), "USD")

    def test_le_gt_ge(self):
        a = Money(Decimal("1.00"), "RUB")
        b = Money(Decimal("2.00"), "RUB")
        assert a <= b
        assert b > a
        assert b >= a


class TestMinorUnits:
    def test_to_minor_units(self):
        assert Money(Decimal("12.34"), "RUB").to_minor_units() == 1234

    def test_to_minor_units_rounds_half_up(self):
        assert Money(Decimal("1.235"), "RUB").to_minor_units() == 124

    def test_round_trip(self):
        original = 12345
        assert Money.from_minor_units(original, "USD").to_minor_units() == original


class TestMoneyInheritsDomainError:
    def test_currency_mismatch_is_domain_error(self):
        assert issubclass(CurrencyMismatchError, DomainError)
