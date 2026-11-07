"""Use cases for the debts bounded context."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from debts.application.dto import (
    CreateDebtInput,
    DebtDTO,
    DebtEventDTO,
    DebtPaymentDTO,
    RepayDebtInput,
    UpdateDebtInput,
)
from debts.application.ports import DebtPaymentRepository, DebtRepository
from debts.domain.entities import Debt, DebtPayment
from debts.domain.enums import DebtDirection, DebtEventKind
from debts.domain.exceptions import (
    DebtAlreadyClosedError,
    DebtBelowRepaidError,
    DebtNotFoundError,
    ExcessiveRepaymentError,
)
from finances.application.ports import AccountRepository, BalanceReader
from finances.application.use_cases import account_refs, require_funds
from finances.domain.exceptions import AccountArchivedError, AccountNotFoundError
from shared.application.patch import apply_patch
from shared.application.ports import UnitOfWork
from shared.domain.clock import Clock
from shared.domain.money import Money
from shared.exceptions import ValidationError


def _dto(d: Debt) -> DebtDTO:
    return DebtDTO(
        id=d.id,
        person_name=d.person_name,
        direction=d.direction,
        amount=d.amount,
        remaining=d.remaining if d.remaining is not None else d.amount,
        due_date=d.due_date,
        is_closed=d.is_closed,
        note=d.note,
        created_at=d.created_at,
    )


class CreateDebt:
    """Opening a debt records it only; balances move with repayments."""

    def __init__(self, debts: DebtRepository, clock: Clock) -> None:
        self._debts = debts
        self._clock = clock

    def execute(self, user_id: UUID, data: CreateDebtInput) -> DebtDTO:
        debt = Debt(
            user_id=user_id,
            person_name=data.person_name,
            direction=data.direction,
            amount=Money.from_minor_units(data.amount_minor, data.currency),
            due_date=data.due_date,
            note=data.note,
            created_at=self._clock.now(),
        )
        return _dto(self._debts.add(debt))


class UpdateDebt:
    """Edit a debt; a new amount keeps the repaid part and recomputes the rest.

    Raising the amount of a closed debt reopens it; lowering it to what is
    repaid closes it.
    """

    def __init__(self, debts: DebtRepository, uow: UnitOfWork) -> None:
        self._debts = debts
        self._uow = uow

    def execute(self, user_id: UUID, debt_id: UUID, data: UpdateDebtInput) -> DebtDTO:
        with self._uow:
            debt = self._debts.get_for_update(debt_id, user_id)
            if debt is None:
                raise DebtNotFoundError(debt_id)
            paid = debt.paid_amount
            currency = debt.amount.currency
            updated = apply_patch(
                debt,
                data,
                fields={"amount_minor": ("amount", lambda m: Money.from_minor_units(m, currency))},
                nullable={"due_date"},
            )
            if updated.amount < paid:
                raise DebtBelowRepaidError
            remaining = updated.amount - paid
            updated = replace(updated, remaining=remaining, is_closed=remaining.is_zero())
            saved = self._debts.update(updated)
        return _dto(saved)


class ListDebts:
    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    def execute(self, user_id: UUID) -> list[DebtDTO]:
        return [_dto(d) for d in self._debts.list_for_user(user_id)]


class GetDebtHistory:
    """The opening of a debt and its repayments, newest first."""

    def __init__(
        self, debts: DebtRepository, payments: DebtPaymentRepository, accounts: AccountRepository
    ) -> None:
        self._debts = debts
        self._payments = payments
        self._accounts = accounts

    def execute(self, user_id: UUID, debt_id: UUID) -> list[DebtEventDTO]:
        debt = self._debts.get_by_id(debt_id, user_id)
        if debt is None:
            raise DebtNotFoundError(debt_id)
        refs = account_refs(self._accounts, user_id)
        events = [
            DebtEventDTO(
                id=p.id,
                kind=DebtEventKind.REPAYMENT,
                amount=p.amount,
                date=p.date,
                account=refs.get(p.account_id),
            )
            for p in self._payments.list_for_debt(debt_id)
        ]
        if debt.created_at is not None:
            events.append(
                DebtEventDTO(
                    id=debt.id,
                    kind=DebtEventKind.OPENED,
                    amount=debt.amount,
                    date=debt.created_at.date(),
                    account=None,
                )
            )
        # The opening goes last among same-day events: it happened first.
        events.sort(key=lambda e: (e.date, e.kind is DebtEventKind.REPAYMENT), reverse=True)
        return events


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
        balances: BalanceReader,
        uow: UnitOfWork,
    ) -> None:
        self._debts = debts
        self._payments = payments
        self._accounts = accounts
        self._balances = balances
        self._uow = uow

    def execute(self, user_id: UUID, debt_id: UUID, data: RepayDebtInput) -> DebtPaymentDTO:
        """Repay a debt from (``i_owe``) or into (``owed_to_me``) an account."""
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        if account.is_archived:
            raise AccountArchivedError
        with self._uow:
            # Re-read under a row lock so concurrent repayments cannot both pass
            # the remaining-balance check.
            debt = self._debts.get_for_update(debt_id, user_id)
            if debt is None:
                raise DebtNotFoundError(debt_id)
            if debt.is_closed:
                raise DebtAlreadyClosedError
            amount = Money.from_minor_units(data.amount_minor, debt.amount.currency)
            if account.currency.value != amount.currency:
                msg = f"Account currency must match debt currency {amount.currency}."
                raise ValidationError(msg, field="account_id", field_code="currency_mismatch")
            if amount > debt.remaining:
                raise ExcessiveRepaymentError
            if debt.direction is DebtDirection.I_OWE:
                require_funds(self._balances, account, amount, "amount_minor")
            new_remaining = debt.remaining - amount
            payment = self._payments.add(
                DebtPayment(
                    debt_id=debt_id, account_id=data.account_id, amount=amount, date=data.date
                )
            )
            self._debts.update(
                replace(debt, remaining=new_remaining, is_closed=new_remaining.is_zero())
            )
        return DebtPaymentDTO(
            id=payment.id,
            debt_id=payment.debt_id,
            account_id=payment.account_id,
            amount=payment.amount,
            date=payment.date,
        )


class DeleteDebt:
    def __init__(self, debts: DebtRepository) -> None:
        self._debts = debts

    def execute(self, user_id: UUID, debt_id: UUID) -> None:
        if not self._debts.delete(debt_id, user_id):
            raise DebtNotFoundError(debt_id)
