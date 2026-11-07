from datetime import date
from uuid import uuid4

import pytest

from debts.application.dto import CreateDebtInput, RepayDebtInput, UpdateDebtInput
from debts.application.use_cases import (
    CreateDebt,
    GetDebtDetail,
    GetDebtHistory,
    RepayDebt,
    UpdateDebt,
)
from debts.domain.enums import DebtEventKind
from debts.domain.exceptions import (
    DebtAlreadyClosedError,
    DebtBelowRepaidError,
    ExcessiveRepaymentError,
)
from finances.application.dto import CreateAccountInput
from finances.application.use_cases import CreateAccount, GetAccountDetail
from finances.domain.exceptions import InsufficientFundsError
from tests.fakes import (
    FakeClock,
    FakeUnitOfWork,
    InMemoryAccountRepository,
    InMemoryBalanceReader,
    InMemoryDebtPaymentRepository,
    InMemoryDebtRepository,
)

USER = uuid4()
DAY = date(2026, 3, 15)


class World:
    def __init__(self, initial_minor: int = 5000_00) -> None:
        self.accounts = InMemoryAccountRepository()
        self.debts = InMemoryDebtRepository()
        self.payments = InMemoryDebtPaymentRepository()
        self.balances = InMemoryBalanceReader(payments=self.payments, debts=self.debts)
        self.account_id = (
            CreateAccount(self.accounts)
            .execute(
                USER,
                CreateAccountInput(
                    name="Счёт",
                    type="debit",
                    currency="RUB",
                    initial_balance_minor=initial_minor,
                ),
            )
            .id
        )

    def debt(self, direction="i_owe", amount_minor=1000_00):
        return CreateDebt(self.debts, FakeClock(DAY)).execute(
            USER,
            CreateDebtInput(
                person_name="Иван",
                direction=direction,
                amount_minor=amount_minor,
                currency="RUB",
                note="на ремонт",
            ),
        )

    def repay(self, debt_id, amount_minor):
        return RepayDebt(
            self.debts, self.payments, self.accounts, self.balances, FakeUnitOfWork()
        ).execute(
            USER,
            debt_id,
            RepayDebtInput(account_id=self.account_id, amount_minor=amount_minor, date=DAY),
        )

    def update(self, debt_id, **fields):
        return UpdateDebt(self.debts, FakeUnitOfWork()).execute(
            USER, debt_id, UpdateDebtInput.model_validate(fields)
        )

    def detail(self, debt_id):
        return GetDebtDetail(self.debts, self.payments).execute(USER, debt_id)

    def balance(self) -> int:
        account = GetAccountDetail(self.accounts, self.balances).execute(USER, self.account_id)
        return account.balance.to_minor_units()


class TestRepayDebt:
    def test_partial_repayment(self):
        w = World()
        debt = w.debt()
        w.repay(debt.id, 400_00)
        detail = w.detail(debt.id)
        assert detail.remaining.to_minor_units() == 600_00
        assert detail.is_closed is False

    def test_full_repayment_closes_debt(self):
        w = World()
        debt = w.debt()
        w.repay(debt.id, 1000_00)
        assert w.detail(debt.id).is_closed is True

    def test_excessive_repayment_rejected(self):
        w = World()
        debt = w.debt()
        with pytest.raises(ExcessiveRepaymentError):
            w.repay(debt.id, 1001_00)

    def test_repay_closed_debt_rejected(self):
        w = World()
        debt = w.debt()
        w.repay(debt.id, 1000_00)
        with pytest.raises(DebtAlreadyClosedError):
            w.repay(debt.id, 1_00)

    def test_i_owe_repayment_takes_money_from_the_account(self):
        w = World()
        w.repay(w.debt("i_owe").id, 300_00)
        assert w.balance() == 4700_00

    def test_owed_to_me_repayment_brings_money_in(self):
        w = World(initial_minor=0)
        w.repay(w.debt("owed_to_me").id, 300_00)
        assert w.balance() == 300_00

    def test_i_owe_repayment_needs_funds(self):
        w = World(initial_minor=100_00)
        with pytest.raises(InsufficientFundsError):
            w.repay(w.debt("i_owe").id, 300_00)


class TestUpdateDebt:
    def test_new_amount_keeps_the_repaid_part(self):
        w = World()
        debt = w.debt()
        w.repay(debt.id, 400_00)
        updated = w.update(debt.id, amount_minor=1500_00, note="")
        assert updated.amount.to_minor_units() == 1500_00
        assert updated.remaining.to_minor_units() == 1100_00
        assert updated.note == ""

    def test_amount_below_repaid_rejected(self):
        w = World()
        debt = w.debt()
        w.repay(debt.id, 400_00)
        with pytest.raises(DebtBelowRepaidError):
            w.update(debt.id, amount_minor=300_00)

    def test_raising_the_amount_reopens_a_closed_debt(self):
        w = World()
        debt = w.debt()
        w.repay(debt.id, 1000_00)
        updated = w.update(debt.id, amount_minor=1200_00)
        assert updated.is_closed is False
        assert updated.remaining.to_minor_units() == 200_00


class TestDebtHistory:
    def test_opening_and_repayments_newest_first(self):
        w = World()
        debt = w.debt()
        assert debt.note == "на ремонт"
        assert debt.created_at is not None
        w.repay(debt.id, 400_00)
        events = GetDebtHistory(w.debts, w.payments, w.accounts).execute(USER, debt.id)
        assert [e.kind for e in events] == [DebtEventKind.REPAYMENT, DebtEventKind.OPENED]
        assert events[0].account.name == "Счёт"
        assert events[1].amount.to_minor_units() == 1000_00
        assert events[1].account is None
