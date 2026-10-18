from datetime import date
from uuid import uuid4

import pytest

from finances.domain.enums import TransactionType
from recurring.domain.entities import RecurringTransaction
from recurring.domain.enums import RecurringFrequency
from shared.domain.money import Money
from shared.exceptions import ValidationError

USER = uuid4()
ACCT = uuid4()


class TestRecurringTransaction:
    def test_creates(self):
        r = RecurringTransaction(
            user_id=USER,
            name="Аренда",
            amount=Money.from_minor_units(40000_00, "RUB"),
            type=TransactionType.EXPENSE,
            account_id=ACCT,
            frequency=RecurringFrequency.MONTHLY,
            next_run=date(2026, 4, 1),
        )
        assert r.is_active is True

    def test_rejects_zero_amount(self):
        with pytest.raises(ValidationError):
            RecurringTransaction(
                user_id=USER,
                name="X",
                amount=Money.zero("RUB"),
                type=TransactionType.EXPENSE,
                account_id=ACCT,
                frequency=RecurringFrequency.MONTHLY,
                next_run=date(2026, 4, 1),
            )

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            RecurringTransaction(
                user_id=USER,
                name=" ",
                amount=Money.from_minor_units(1, "RUB"),
                type=TransactionType.EXPENSE,
                account_id=ACCT,
                frequency=RecurringFrequency.MONTHLY,
                next_run=date(2026, 4, 1),
            )
