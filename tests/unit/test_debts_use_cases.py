from datetime import date
from uuid import uuid4

import pytest

from debts.application.dto import CreateDebtInput, RepayDebtInput
from debts.application.use_cases import CreateDebt, GetDebtDetail, RepayDebt
from debts.domain.exceptions import DebtAlreadyClosedError, ExcessiveRepaymentError
from finances.application.dto import CreateAccountInput
from finances.application.use_cases import CreateAccount
from tests.fakes import (
    FakeUnitOfWork,
    InMemoryAccountRepository,
    InMemoryDebtPaymentRepository,
    InMemoryDebtRepository,
)

USER = uuid4()


def _account():
    repo = InMemoryAccountRepository()
    dto = CreateAccount(repo).execute(
        USER, CreateAccountInput(name="Счёт", type="debit", currency="RUB")
    )
    return repo, dto.id


class TestRepayDebt:
    def test_partial_repayment(self):
        accounts, acct_id = _account()
        debts = InMemoryDebtRepository()
        payments = InMemoryDebtPaymentRepository()
        debt = CreateDebt(debts).execute(
            USER,
            CreateDebtInput(
                person_name="Иван", direction="i_owe", amount_minor=1000_00, currency="RUB"
            ),
        )
        RepayDebt(debts, payments, accounts, FakeUnitOfWork()).execute(
            USER,
            debt.id,
            RepayDebtInput(account_id=acct_id, amount_minor=400_00, date=date(2026, 3, 15)),
        )
        detail = GetDebtDetail(debts, payments).execute(USER, debt.id)
        assert detail.remaining.to_minor_units() == 600_00
        assert detail.is_closed is False

    def test_full_repayment_closes_debt(self):
        accounts, acct_id = _account()
        debts = InMemoryDebtRepository()
        payments = InMemoryDebtPaymentRepository()
        debt = CreateDebt(debts).execute(
            USER,
            CreateDebtInput(
                person_name="Иван", direction="i_owe", amount_minor=1000_00, currency="RUB"
            ),
        )
        RepayDebt(debts, payments, accounts, FakeUnitOfWork()).execute(
            USER,
            debt.id,
            RepayDebtInput(account_id=acct_id, amount_minor=1000_00, date=date(2026, 3, 15)),
        )
        detail = GetDebtDetail(debts, payments).execute(USER, debt.id)
        assert detail.is_closed is True

    def test_excessive_repayment_rejected(self):
        accounts, acct_id = _account()
        debts = InMemoryDebtRepository()
        payments = InMemoryDebtPaymentRepository()
        debt = CreateDebt(debts).execute(
            USER,
            CreateDebtInput(
                person_name="Иван", direction="i_owe", amount_minor=1000_00, currency="RUB"
            ),
        )
        with pytest.raises(ExcessiveRepaymentError):
            RepayDebt(debts, payments, accounts, FakeUnitOfWork()).execute(
                USER,
                debt.id,
                RepayDebtInput(account_id=acct_id, amount_minor=1001_00, date=date(2026, 3, 15)),
            )

    def test_repay_closed_debt_rejected(self):
        accounts, acct_id = _account()
        debts = InMemoryDebtRepository()
        payments = InMemoryDebtPaymentRepository()
        debt = CreateDebt(debts).execute(
            USER,
            CreateDebtInput(
                person_name="Иван", direction="i_owe", amount_minor=1000_00, currency="RUB"
            ),
        )
        RepayDebt(debts, payments, accounts, FakeUnitOfWork()).execute(
            USER,
            debt.id,
            RepayDebtInput(account_id=acct_id, amount_minor=1000_00, date=date(2026, 3, 15)),
        )
        with pytest.raises(DebtAlreadyClosedError):
            RepayDebt(debts, payments, accounts, FakeUnitOfWork()).execute(
                USER,
                debt.id,
                RepayDebtInput(account_id=acct_id, amount_minor=1_00, date=date(2026, 3, 15)),
            )
