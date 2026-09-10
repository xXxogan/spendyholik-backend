"""Use cases for the recurring bounded context."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from dateutil.relativedelta import relativedelta

from finances.application.ports import AccountRepository, TransactionRepository
from finances.domain.entities import Transaction
from finances.domain.enums import TransactionType
from finances.domain.exceptions import AccountNotFoundError
from recurring.application.dto import (
    CreateRecurringInput,
    RecurringDTO,
    RunDueRecurringResultDTO,
    UpdateRecurringInput,
)
from recurring.application.ports import RecurringTransactionRepository
from recurring.domain.entities import RecurringTransaction
from recurring.domain.enums import RecurringFrequency
from recurring.domain.exceptions import RecurringTransactionNotFoundError
from shared.application.ports import UnitOfWork
from shared.domain.clock import Clock
from shared.domain.money import Money


def _dto(r: RecurringTransaction) -> RecurringDTO:
    return RecurringDTO(
        id=r.id,
        name=r.name,
        amount=r.amount,
        type=r.type,
        account_id=r.account_id,
        category_id=r.category_id,
        frequency=r.frequency,
        next_run=r.next_run,
        is_active=r.is_active,
    )


def _advance(next_run: date, frequency: RecurringFrequency) -> date:
    if frequency is RecurringFrequency.WEEKLY:
        return next_run + relativedelta(weeks=1)
    if frequency is RecurringFrequency.MONTHLY:
        return next_run + relativedelta(months=1)
    return next_run + relativedelta(years=1)


class CreateRecurring:
    def __init__(self, recurring: RecurringTransactionRepository, accounts: AccountRepository) -> None:
        self._recurring = recurring
        self._accounts = accounts

    def execute(self, user_id: UUID, data: CreateRecurringInput) -> RecurringDTO:
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        entity = RecurringTransaction(
            user_id=user_id,
            name=data.name,
            amount=Money.from_minor_units(data.amount_minor, account.currency.value),
            type=data.type,
            account_id=data.account_id,
            category_id=data.category_id,
            frequency=data.frequency,
            next_run=data.next_run,
            is_active=data.is_active,
        )
        return _dto(self._recurring.add(entity))


class UpdateRecurring:
    def __init__(self, recurring: RecurringTransactionRepository, accounts: AccountRepository) -> None:
        self._recurring = recurring
        self._accounts = accounts

    def execute(self, user_id: UUID, recurring_id: UUID, data: UpdateRecurringInput) -> RecurringDTO:
        r = self._recurring.get_by_id(recurring_id, user_id)
        if r is None:
            raise RecurringTransactionNotFoundError(recurring_id)
        account_id = data.account_id if data.account_id is not None else r.account_id
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        updated = RecurringTransaction(
            id=r.id,
            user_id=user_id,
            name=data.name if data.name is not None else r.name,
            amount=(
                r.amount
                if data.amount_minor is None
                else Money.from_minor_units(data.amount_minor, account.currency.value)
            ),
            type=r.type,
            account_id=account_id,
            category_id=r.category_id if data.category_id is None else data.category_id,
            frequency=data.frequency if data.frequency is not None else r.frequency,
            next_run=data.next_run if data.next_run is not None else r.next_run,
            is_active=r.is_active if data.is_active is None else data.is_active,
        )
        return _dto(self._recurring.update(updated))


class ToggleRecurring:
    def __init__(self, recurring: RecurringTransactionRepository) -> None:
        self._recurring = recurring

    def execute(self, user_id: UUID, recurring_id: UUID, is_active: bool) -> RecurringDTO:
        r = self._recurring.get_by_id(recurring_id, user_id)
        if r is None:
            raise RecurringTransactionNotFoundError(recurring_id)
        updated = RecurringTransaction(
            id=r.id, user_id=r.user_id, name=r.name, amount=r.amount, type=r.type,
            account_id=r.account_id, category_id=r.category_id, frequency=r.frequency,
            next_run=r.next_run, is_active=is_active,
        )
        return _dto(self._recurring.update(updated))


class ListRecurring:
    def __init__(self, recurring: RecurringTransactionRepository) -> None:
        self._recurring = recurring

    def execute(self, user_id: UUID) -> list[RecurringDTO]:
        return [_dto(r) for r in self._recurring.list_for_user(user_id)]


class RunDueRecurring:
    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        transactions: TransactionRepository,
        accounts: AccountRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._recurring = recurring
        self._transactions = transactions
        self._accounts = accounts
        self._uow = uow
        self._clock = clock

    def execute(self) -> RunDueRecurringResultDTO:
        today = self._clock.now().date()
        due = self._recurring.list_due(today)
        generated = 0
        skipped = 0
        with self._uow:
            for r in due:
                if not r.is_active:
                    skipped += 1
                    continue
                if self._transactions.exists_for_source(r.user_id, r.id, today):
                    skipped += 1
                    continue
                account = self._accounts.get_by_id(r.account_id, r.user_id)
                if account is None or account.is_archived:
                    skipped += 1
                    continue
                self._transactions.add(
                    Transaction(
                        user_id=r.user_id,
                        account_id=r.account_id,
                        category_id=r.category_id,
                        type=r.type,
                        amount=r.amount,
                        date=today,
                        recurring_source_id=r.id,
                    )
                )
                advanced = RecurringTransaction(
                    id=r.id, user_id=r.user_id, name=r.name, amount=r.amount, type=r.type,
                    account_id=r.account_id, category_id=r.category_id, frequency=r.frequency,
                    next_run=_advance(today, r.frequency), is_active=r.is_active,
                )
                self._recurring.update(advanced)
                generated += 1
        return RunDueRecurringResultDTO(generated=generated, skipped=skipped)
