from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import AccountType, BudgetPeriod, TransactionType
from finances.domain.value_objects import CategoryColor
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money
from shared.exceptions import ValidationError

USER = uuid4()


class TestAccount:
    def test_creates_valid_account(self):
        acct = Account(
            user_id=USER,
            name="Карта Тинькофф",
            type=AccountType.DEBIT,
            currency=CurrencyCode("RUB"),
            initial_balance=Money.from_minor_units(5000_00, "RUB"),
        )
        assert acct.name == "Карта Тинькофф"
        assert acct.initial_balance.to_minor_units() == 5000_00

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            Account(user_id=USER, name="  ", type=AccountType.CASH, currency=CurrencyCode("RUB"))

    def test_rejects_currency_mismatch(self):
        with pytest.raises(ValidationError):
            Account(
                user_id=USER,
                name="X",
                type=AccountType.CASH,
                currency=CurrencyCode("RUB"),
                initial_balance=Money.from_minor_units(100, "USD"),
            )

    def test_rejects_bad_last4(self):
        with pytest.raises(ValidationError):
            Account(
                user_id=USER,
                name="X",
                type=AccountType.DEBIT,
                currency=CurrencyCode("RUB"),
                last4="12a4",
            )

    def test_rejects_negative_credit_limit(self):
        with pytest.raises(ValidationError):
            Account(
                user_id=USER,
                name="X",
                type=AccountType.CREDIT,
                currency=CurrencyCode("RUB"),
                credit_limit=Money.from_minor_units(-1, "RUB"),
            )


class TestCategory:
    def test_creates_category(self):
        cat = Category(user_id=USER, name="Продукты", type=TransactionType.EXPENSE)
        assert cat.icon == "tag"
        assert str(cat.color) == "default"

    def test_rejects_self_parent(self):
        cat_id = uuid4()
        with pytest.raises(ValidationError):
            Category(
                user_id=USER, name="X", type=TransactionType.EXPENSE, parent_id=cat_id, id=cat_id
            )


class TestTransaction:
    def test_transfer_requires_destination(self):
        with pytest.raises(ValidationError):
            Transaction(
                user_id=USER,
                account_id=uuid4(),
                type=TransactionType.TRANSFER,
                amount=Money.from_minor_units(100, "RUB"),
                date=date(2026, 3, 15),
            )

    def test_transfer_to_same_account_rejected(self):
        acct = uuid4()
        with pytest.raises(ValidationError):
            Transaction(
                user_id=USER,
                account_id=acct,
                type=TransactionType.TRANSFER,
                amount=Money.from_minor_units(100, "RUB"),
                date=date(2026, 3, 15),
                transfer_to_account_id=acct,
            )

    def test_non_transfer_rejects_destination(self):
        with pytest.raises(ValidationError):
            Transaction(
                user_id=USER,
                account_id=uuid4(),
                type=TransactionType.EXPENSE,
                amount=Money.from_minor_units(100, "RUB"),
                date=date(2026, 3, 15),
                transfer_to_account_id=uuid4(),
            )

    def test_valid_expense(self):
        tx = Transaction(
            user_id=USER,
            account_id=uuid4(),
            type=TransactionType.EXPENSE,
            amount=Money.from_minor_units(1240_00, "RUB"),
            date=date(2026, 3, 15),
        )
        assert tx.amount.to_minor_units() == 1240_00


class TestBudget:
    def test_creates_budget(self):
        b = Budget(
            user_id=USER, category_id=uuid4(), amount=Money.from_minor_units(30000_00, "RUB")
        )
        assert b.period is BudgetPeriod.MONTHLY

    def test_rejects_non_positive_amount(self):
        with pytest.raises(ValidationError):
            Budget(user_id=USER, category_id=uuid4(), amount=Money.zero("RUB"))


class TestExchangeRate:
    def test_creates_rate(self):
        r = ExchangeRate(
            base=CurrencyCode("USD"),
            target=CurrencyCode("RUB"),
            rate=Decimal("90.5"),
            date=date(2026, 3, 15),
        )
        assert r.rate == Decimal("90.5")

    def test_rejects_same_currency(self):
        with pytest.raises(ValidationError):
            ExchangeRate(
                base=CurrencyCode("USD"),
                target=CurrencyCode("USD"),
                rate=Decimal("1"),
                date=date(2026, 3, 15),
            )

    def test_rejects_non_positive_rate(self):
        with pytest.raises(ValidationError):
            ExchangeRate(
                base=CurrencyCode("USD"),
                target=CurrencyCode("RUB"),
                rate=Decimal("0"),
                date=date(2026, 3, 15),
            )


class TestCategoryColor:
    def test_lowercases_and_validates(self):
        assert CategoryColor("Cat-Food").value == "cat-food"

    def test_rejects_invalid(self):
        with pytest.raises(ValidationError):
            CategoryColor("not a color!")


class TestEnums:
    def test_transaction_types(self):
        assert {t.value for t in TransactionType} == {"expense", "income", "transfer"}

    def test_account_types(self):
        assert {t.value for t in AccountType} == {"debit", "cash", "savings", "credit"}

    def test_budget_periods(self):
        assert {p.value for p in BudgetPeriod} == {"monthly", "weekly", "one_time"}
