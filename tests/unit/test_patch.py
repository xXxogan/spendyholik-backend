from datetime import date
from uuid import uuid4

import pytest

from finances.application.dto import (
    CreateAccountInput,
    CreateCategoryInput,
    CreateTransactionInput,
    UpdateAccountInput,
    UpdateTransactionInput,
)
from finances.application.use_cases import (
    CreateAccount,
    CreateCategory,
    CreateTransaction,
    UpdateAccount,
    UpdateTransaction,
)
from finances.domain.entities import Account
from finances.domain.enums import AccountType
from shared.domain.currency_code import CurrencyCode
from shared.exceptions import ValidationError
from tests.fakes import (
    InMemoryAccountRepository,
    InMemoryCategoryRepository,
    InMemoryTransactionRepository,
)

USER = uuid4()


def _world():
    accounts = InMemoryAccountRepository()
    categories = InMemoryCategoryRepository()
    transactions = InMemoryTransactionRepository()
    rub = CreateAccount(accounts).execute(
        USER, CreateAccountInput(name="Карта", type="debit", currency="RUB", last4="1234")
    )
    food = CreateCategory(categories).execute(USER, CreateCategoryInput(name="Еда", type="expense"))
    tx = CreateTransaction(accounts, categories, transactions).execute(
        USER,
        CreateTransactionInput(
            account_id=rub.id,
            type="expense",
            amount_minor=500_00,
            date=date(2026, 3, 1),
            category_id=food.id,
            note="обед",
        ),
    )
    return accounts, categories, transactions, rub, tx


def test_omitted_fields_are_kept_and_null_clears_nullable_ones():
    accounts, categories, transactions, _, tx = _world()
    update = UpdateTransaction(accounts, categories, transactions)
    updated = update.execute(
        USER, tx.id, UpdateTransactionInput.model_validate({"category_id": None})
    )
    assert updated.category_id is None
    assert updated.note == "обед"
    assert updated.amount.to_minor_units() == 500_00


def test_null_for_required_field_is_rejected():
    accounts, _, _, rub, _ = _world()
    with pytest.raises(ValidationError):
        UpdateAccount(accounts).execute(
            USER, rub.id, UpdateAccountInput.model_validate({"name": None})
        )


def test_last4_can_be_cleared():
    accounts, _, _, rub, _ = _world()
    updated = UpdateAccount(accounts).execute(
        USER, rub.id, UpdateAccountInput.model_validate({"last4": None})
    )
    assert updated.last4 is None


def test_moving_transaction_to_other_currency_redenominates_amount():
    accounts, categories, transactions, _, tx = _world()
    usd = CreateAccount(accounts).execute(
        USER, CreateAccountInput(name="USD", type="debit", currency="USD")
    )
    updated = UpdateTransaction(accounts, categories, transactions).execute(
        USER, tx.id, UpdateTransactionInput(account_id=usd.id)
    )
    assert updated.amount.currency == "USD"
    assert updated.amount.to_minor_units() == 500_00


def test_account_default_balance_uses_account_currency():
    account = Account(
        user_id=USER, name="USD", type=AccountType.DEBIT, currency=CurrencyCode("USD")
    )
    assert account.initial_balance.currency == "USD"
