"""Use cases for the debts bounded context."""

from __future__ import annotations

from uuid import UUID

from debts.application.dto import (
    CreateDebtInput,
    DebtDTO,
    DebtPaymentDTO,
    RepayDebtInput,
    UpdateDebtInput,
)
from debts.application.ports import DebtPaymentRepository, DebtRepository
from debts.domain.entities import Debt, DebtPayment
from debts.domain.enums import DebtDirection
from debts.domain.exceptions import (
    DebtAlreadyClosedError,
    DebtNotFoundError,
    ExcessiveRepaymentError,
)
from finances.application.ports import AccountRepository
from finances.domain.exceptions import AccountNotFoundError
from shared.application.ports import UnitOfWork
from shared.domain.money import Money


def _dto(d: Debt) -> DebtDTO:
    return DebtDTO(
        id=d.id,
        person_name=d.person_name,
        direction=d.direction,
        amount=d.amount,
        remaining=d.remaining if d.remaining is not None else d.amount,
        due_date=d.due_date,
        is_closed=d.is_closed,
    )


class CreateDebt:
    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    def execute(self, user_id: UUID, data: CreateDebtInput) -> DebtDTO:
        debt = Debt(
            user_id=user_id,
            person_name=data.person_name,
            direction=data.direction,
            amount=Money.from_minor_units(data.amount_minor, data.currency),
            due_date=data.due_date,
        )
        return _dto(self._debts.add(debt))


class UpdateDebt:
    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    def execute(self, user_id: UUID, debt_id: UUID, data: UpdateDebtInput) -> DebtDTO:
        debt = self._debts.get_by_id(debt_id, user_id)
        if debt is None:
            raise DebtNotFoundError(debt_id)
        if debt.is_closed:
            raise DebtAlreadyClosedError
        updated = Debt(
            id=debt.id,
            user_id=user_id,
            person_name=data.person_name if data.person_name is not None else debt.person_name,
            direction=debt.direction,
            amount=debt.amount,
            remaining=debt.remaining,
            due_date=debt.due_date if data.due_date is None else data.due_date,
            is_closed=debt.is_closed,
        )
        return _dto(self._debts.update(updated))


class ListDebts:
    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    def execute(self, user_id: UUID) -> list[DebtDTO]:
        return [_dto(d) for d in self._debts.list_for_user(user_id)]


class GetDebtDetail:
    def __init__(self, debts: DebtRepository, payments: DebtPaymentRepository) -> None:
        self._debts = debts
        self._payments = payments

    def execute(self, user_id: UUID, debt_id: UUID) -> DebtDTO:
        debt = self._debts.get_by_id(debt_id, user_id)
        if debt is None:
            raise DebtNotFoundError(debt_id)
        return _dto(debt)


class RepayDebt:
    def __init__(
        self,
        debts: DebtRepository,
        payments: DebtPaymentRepository,
        accounts: AccountRepository,
        uow: UnitOfWork,
    ) -> None:
        self._debts = debts
        self._payments = payments
        self._accounts = accounts
        self._uow = uow

    def execute(self, user_id: UUID, debt_id: UUID, data: RepayDebtInput) -> DebtPaymentDTO:
        debt = self._debts.get_by_id(debt_id, user_id)
        if debt is None:
            raise DebtNotFoundError(debt_id)
        if debt.is_closed:
            raise DebtAlreadyClosedError
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        amount = Money.from_minor_units(data.amount_minor, debt.amount.currency)
        if amount > debt.remaining:
            raise ExcessiveRepaymentError
        new_remaining = debt.remaining - amount
        with self._uow:
            payment = self._payments.add(
                DebtPayment(debt_id=debt_id, account_id=data.account_id, amount=amount, date=data.date)
            )
            self._debts.update(
                Debt(
                    id=debt.id,
                    user_id=user_id,
                    person_name=debt.person_name,
                    direction=debt.direction,
                    amount=debt.amount,
                    remaining=new_remaining,
                    due_date=debt.due_date,
                    is_closed=new_remaining.is_zero(),
                )
            )
        return DebtPaymentDTO(
            id=payment.id,
            debt_id=payment.debt_id,
            account_id=payment.account_id,
            amount=payment.amount,
            date=payment.date,
        )
