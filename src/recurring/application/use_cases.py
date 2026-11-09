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
    TransactionObserver,
    TransactionRepository,
)
from finances.application.use_cases import account_refs, category_ref, require_category
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


def _dto(r: RecurringTransaction, accounts=None, categories=None) -> RecurringDTO:
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
        anchor_date=r.anchor,
        account=(accounts or {}).get(r.account_id),
        category=(categories or {}).get(r.category_id),
    )


class _Renderer:
    """Attaches account and category references (two queries per call)."""

    def __init__(self, accounts: AccountRepository, categories: CategoryRepository) -> None:
        self._accounts = accounts
        self._categories = categories

    def render(self, user_id: UUID, items: list[RecurringTransaction]) -> list[RecurringDTO]:
        accounts = account_refs(self._accounts, user_id)
        categories = {c.id: category_ref(c) for c in self._categories.list_for_user(user_id)}
        return [_dto(r, accounts, categories) for r in items]

    def render_one(self, user_id: UUID, item: RecurringTransaction) -> RecurringDTO:
        return self.render(user_id, [item])[0]


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


def next_on_or_after(anchor: date, frequency: RecurringFrequency, day: date) -> date:
    """First occurrence of the schedule anchored at ``anchor`` that is not before ``day``."""
    return _shift(anchor, frequency, _first_step(anchor, frequency, day))


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
        clock: Clock,
    ) -> None:
        self._recurring = recurring
        self._accounts = accounts
        self._categories = categories
        self._clock = clock
        self._renderer = _Renderer(accounts, categories)

    def execute(self, user_id: UUID, data: CreateRecurringInput) -> RecurringDTO:
        account = self._accounts.get_by_id(data.account_id, user_id)
        if account is None:
            raise AccountNotFoundError(data.account_id)
        _validate_template(self._categories, user_id, data.type, data.category_id)
        next_run = data.next_run
        if next_run is None:
            if data.anchor_date is None:
                msg = "anchor_date or next_run is required."
                raise ValidationError(msg, field="anchor_date", field_code="required")
            next_run = next_on_or_after(data.anchor_date, data.frequency, self._clock.now().date())
        entity = RecurringTransaction(
            user_id=user_id,
            name=data.name,
            amount=Money.from_minor_units(data.amount_minor, account.currency.value),
            type=data.type,
            account_id=data.account_id,
            category_id=data.category_id,
            frequency=data.frequency,
            next_run=next_run,
            anchor=data.anchor_date or next_run,
            is_active=data.is_active,
        )
        return self._renderer.render_one(user_id, self._recurring.add(entity))


class UpdateRecurring:
    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
        clock: Clock,
    ) -> None:
        self._recurring = recurring
        self._accounts = accounts
        self._categories = categories
        self._clock = clock
        self._renderer = _Renderer(accounts, categories)

    def execute(
        self, user_id: UUID, recurring_id: UUID, data: UpdateRecurringInput
    ) -> RecurringDTO:
        r = self._recurring.get_by_id(recurring_id, user_id)
        if r is None:
            raise RecurringTransactionNotFoundError(recurring_id)
        updated = apply_patch(
            r,
            data,
            fields={
                "amount_minor": ("amount", lambda _: r.amount),
                "anchor_date": ("anchor", lambda d: d),
            },
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
        sent = data.model_fields_set
        if "anchor_date" in sent:
            if "next_run" not in sent:
                changes["next_run"] = next_on_or_after(
                    updated.anchor, updated.frequency, self._clock.now().date()
                )
        elif {"next_run", "frequency"} & sent:
            # A rescheduled template starts counting from its new first run.
            changes["anchor"] = updated.next_run
        updated = replace(updated, **changes)
        return self._renderer.render_one(user_id, self._recurring.update(updated))


class ToggleRecurring:
    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
    ) -> None:
        self._recurring = recurring
        self._renderer = _Renderer(accounts, categories)

    def execute(self, user_id: UUID, recurring_id: UUID, is_active: bool) -> RecurringDTO:
        r = self._recurring.get_by_id(recurring_id, user_id)
        if r is None:
            raise RecurringTransactionNotFoundError(recurring_id)
        saved = self._recurring.update(replace(r, is_active=is_active))
        return self._renderer.render_one(user_id, saved)


class DeleteRecurring:
    def __init__(self, recurring: RecurringTransactionRepository) -> None:
        self._recurring = recurring

    def execute(self, user_id: UUID, recurring_id: UUID) -> None:
        if not self._recurring.delete(recurring_id, user_id):
            raise RecurringTransactionNotFoundError(recurring_id)


class ListRecurring:
    def __init__(
        self,
        recurring: RecurringTransactionRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
    ) -> None:
        self._recurring = recurring
        self._renderer = _Renderer(accounts, categories)

    def execute(self, user_id: UUID) -> list[RecurringDTO]:
        return self._renderer.render(user_id, self._recurring.list_for_user(user_id))


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
        observer: TransactionObserver | None = None,
    ) -> None:
        self._recurring = recurring
        self._transactions = transactions
        self._uow = uow
        self._clock = clock
        self._observer = observer

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
            saved = self._transactions.add(
                Transaction(
                    user_id=template.user_id,
                    account_id=template.account_id,
                    category_id=template.category_id,
                    type=template.type,
                    amount=template.amount,
                    date=on,
                    title=template.name,
                    recurring_source_id=template.id,
                )
            )
            if self._observer is not None:
                self._observer.changed(template.user_id, None, saved)
            created += 1
        self._recurring.update(replace(template, next_run=next_run))
        return created, existing
