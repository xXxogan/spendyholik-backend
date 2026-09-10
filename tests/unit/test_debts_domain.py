from datetime import date
from uuid import uuid4

import pytest

from debts.domain.entities import Debt, DebtPayment
from debts.domain.enums import DebtDirection
from shared.domain.money import Money
from shared.exceptions import ValidationError

USER = uuid4()
ACCT = uuid4()


class TestDebt:
    def test_defaults_remaining_to_amount(self):
        d = Debt(user_id=USER, person_name="Иван", direction=DebtDirection.I_OWE,
                 amount=Money.from_minor_units(1000_00, "RUB"))
        assert d.remaining == d.amount
        assert d.is_closed is False

    def test_paid_amount(self):
        d = Debt(user_id=USER, person_name="Иван", direction=DebtDirection.I_OWE,
                 amount=Money.from_minor_units(1000_00, "RUB"),
                 remaining=Money.from_minor_units(400_00, "RUB"))
        assert d.paid_amount.to_minor_units() == 600_00

    def test_rejects_negative_remaining(self):
        with pytest.raises(ValidationError):
            Debt(user_id=USER, person_name="Иван", direction=DebtDirection.I_OWE,
                 amount=Money.from_minor_units(1000_00, "RUB"),
                 remaining=Money.from_minor_units(-1, "RUB"))

    def test_rejects_closed_with_remaining(self):
        with pytest.raises(ValidationError):
            Debt(user_id=USER, person_name="Иван", direction=DebtDirection.I_OWE,
                 amount=Money.from_minor_units(1000_00, "RUB"), is_closed=True)

    def test_allows_closed_at_zero(self):
        d = Debt(user_id=USER, person_name="Иван", direction=DebtDirection.I_OWE,
                 amount=Money.from_minor_units(1000_00, "RUB"),
                 remaining=Money.zero("RUB"), is_closed=True)
        assert d.is_closed is True


class TestDebtPayment:
    def test_creates(self):
        p = DebtPayment(debt_id=uuid4(), account_id=ACCT,
                        amount=Money.from_minor_units(100_00, "RUB"), date=date(2026, 3, 15))
        assert p.amount.is_positive()

    def test_rejects_non_positive(self):
        with pytest.raises(ValidationError):
            DebtPayment(debt_id=uuid4(), account_id=ACCT,
                        amount=Money.zero("RUB"), date=date(2026, 3, 15))


class TestDebtDirection:
    def test_values(self):
        assert {d.value for d in DebtDirection} == {"i_owe", "owed_to_me"}
