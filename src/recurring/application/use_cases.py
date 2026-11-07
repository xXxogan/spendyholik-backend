"""Use cases for the recurring bounded context."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from uuid import UUID

from dateutil.relativedelta import relativedelta

from finances.application.ports import (
    AccountRepository,
    CategoryRepository,
    TransactionRepository,
)
from finances.application.use_cases import require_category
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
from shared.application.patch import apply_patch
from shared.application.ports import UnitOfWork
from shared.domain.clock import Clock
from shared.domain.money import Money
from shared.exceptions import DomainError, ValidationError

logger = logging.getLogger(__name__)


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


_STEP = {
    RecurringFrequency.WEEKLY: relativedelta(weeks=1),
    RecurringFrequency.MONTHLY: relativedelta(months=1),
    RecurringFrequency.YEARLY: relativedelta(years=1),
}

#: Safety cap on back-filled occurrences per template and run.
MAX_OCCURRENCES_PER_RUN = 400


def _shift(anchor: date, frequency: RecurringFrequency, steps: int) -> date:
    # Offsets are taken from the anchor, not chained, so a template on the 31st
    # does not drift to the 28th after February.
    return anchor + _STEP[frequency] * steps


def _first_step(anchor: date, frequency: RecurringFrequency, on_or_after: date) -> int:
    """Index of the first occurrence of the schedule that falls on/after ``on_or_after``."""
    steps = 0
    while _shift(anchor, frequency, steps) < on_or_after:
        steps += 1
    return steps


def _occurrences(
    anchor: date, frequency: RecurringFrequency, next_run: date, today: date
) -> tuple[list[date], date]:
    """Due dates from ``next_run`` up to ``today`` and the following ``next_run``."""
    step = _first_step(anchor, frequency, next_run)
    result: list[date] = []
    while len(result) < MAX_OCCURRENCES_PER_RUN:
        on = _shift(anchor, frequency, step)
        if on > today:
            break
        result.append(on)
        step += 1
    return result, _shift(anchor, frequency, step)


def _validate_template(
    categories: CategoryRepository,
    user_id: UUID,
    tx_type: TransactionType,
    category_id: UUID | None,
) -> None:
    if tx_type is TransactionType.TRANSFER:
        msg = "Recurring transfers are not supported."
        raise ValidationError(msg)
    require_category(categories, user_id, category_id, tx_type)


class CreateRecurring:
    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
    ) -> None:
        self._recurring = recurring
        self._accounts = accounts
        self._categories = categories

    def execute(self, user_id: UUID, data: CreateRecurringInput) -> RecurringDTO:
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        _validate_template(self._categories, user_id, data.type, data.category_id)
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
    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
    ) -> None:
        self._recurring = recurring
        self._accounts = accounts
        self._categories = categories

    def execute(
        self, user_id: UUID, recurring_id: UUID, data: UpdateRecurringInput
    ) -> RecurringDTO:
        r = self._recurring.get_by_id(recurring_id, user_id)
        if r is None:
            raise RecurringTransactionNotFoundError(recurring_id)
        updated = apply_patch(
            r,
            data,
            fields={"amount_minor": ("amount", lambda _: r.amount)},
            nullable={"category_id"},
        )
        account = self._accounts.get_by_id(updated.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(updated.account_id)
        if "category_id" in data.model_fields_set:
            require_category(self._categories, user_id, updated.category_id, updated.type)
        # Keep the amount in the (possibly new) account's currency.
        minor = r.amount.to_minor_units() if data.amount_minor is None else data.amount_minor
        changes: dict = {"amount": Money.from_minor_units(minor, account.currency.value)}
        if {"next_run", "frequency"} & data.model_fields_set:
            # A rescheduled template starts counting from its new first run.
            changes["anchor"] = updated.next_run
        updated = replace(updated, **changes)
        return _dto(self._recurring.update(updated))


class ToggleRecurring:
    def __init__(self, recurring: RecurringTransactionRepository) -> None:
        self._recurring = recurring

    def execute(self, user_id: UUID, recurring_id: UUID, is_active: bool) -> RecurringDTO:
        r = self._recurring.get_by_id(recurring_id, user_id)
        if r is None:
            raise RecurringTransactionNotFoundError(recurring_id)
        return _dto(self._recurring.update(replace(r, is_active=is_active)))


class DeleteRecurring:
    def __init__(self, recurring: RecurringTransactionRepository) -> None:
        self._recurring = recurring

    def execute(self, user_id: UUID, recurring_id: UUID) -> None:
        if not self._recurring.delete(recurring_id, user_id):
            raise RecurringTransactionNotFoundError(recurring_id)


class ListRecurring:
    def __init__(self, recurring: RecurringTransactionRepository) -> None:
        self._recurring = recurring

    def execute(self, user_id: UUID) -> list[RecurringDTO]:
        return [_dto(r) for r in self._recurring.list_for_user(user_id)]


class RunDueRecurring:
    """Materialise every due occurrence of every active template.

    Missed occurrences (e.g. the scheduler was down) are back-filled with their
    own dates. Each template runs in its own unit of work, so one failure does
    not roll back the others; the ``(recurring_source_id, date)`` uniqueness
    constraint keeps concurrent runs idempotent.
    """

    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        transactions: TransactionRepository,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._recurring = recurring
        self._transactions = transactions
        self._uow = uow
        self._clock = clock

    def execute(self) -> RunDueRecurringResultDTO:
        today = self._clock.now().date()
        generated = 0
        skipped = 0
        for template in self._recurring.list_due(today):
            try:
                with self._uow:
                    created, existing = self._run(template, today)
            except DomainError:
                logger.exception("Recurring template %s failed", template.id)
                skipped += 1
                continue
            generated += created
            skipped += existing
        return RunDueRecurringResultDTO(generated=generated, skipped=skipped)

    def _run(self, template: RecurringTransaction, today: date) -> tuple[int, int]:
        created = existing = 0
        occurrences, next_run = _occurrences(
            template.anchor, template.frequency, template.next_run, today
        )
        for on in occurrences:
            if self._transactions.exists_for_source(template.user_id, template.id, on):
                existing += 1
                continue
            self._transactions.add(
                Transaction(
                    user_id=template.user_id,
                    account_id=template.account_id,
                    category_id=template.category_id,
                    type=template.type,
                    amount=template.amount,
                    date=on,
                    recurring_source_id=template.id,
                )
            )
            created += 1
        self._recurring.update(replace(template, next_run=next_run))
        return created, existing
