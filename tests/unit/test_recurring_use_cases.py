from datetime import date
from uuid import uuid4

import pytest

from finances.application.dto import CreateAccountInput
from finances.application.use_cases import CreateAccount
from recurring.application.dto import CreateRecurringInput, UpdateRecurringInput
from recurring.application.use_cases import CreateRecurring, RunDueRecurring, UpdateRecurring
from shared.exceptions import ValidationError
from tests.fakes import (
    FakeClock,
    FakeUnitOfWork,
    InMemoryAccountRepository,
    InMemoryBalanceReader,
    InMemoryCategoryRepository,
    InMemoryRecurringTransactionRepository,
    InMemoryTransactionRepository,
)

USER = uuid4()
TODAY = date(2026, 3, 15)


def _account():
    repo = InMemoryAccountRepository()
    dto = CreateAccount(repo).execute(
        USER, CreateAccountInput(name="Счёт", type="debit", currency="RUB")
    )
    return repo, dto.id


def _recurring(recurring_repo, accounts, acct_id, next_run=TODAY, frequency="monthly"):
    return CreateRecurring(
        recurring_repo, accounts, InMemoryCategoryRepository(), FakeClock(TODAY)
    ).execute(
        USER,
        CreateRecurringInput(
            name="Аренда",
            amount_minor=40000_00,
            type="expense",
            account_id=acct_id,
            frequency=frequency,
            next_run=next_run,
        ),
    )


def _run(recurring, transactions, today=TODAY):
    return RunDueRecurring(recurring, transactions, FakeUnitOfWork(), FakeClock(today)).execute()


def _dates(transactions):
    return sorted(t.date for t in transactions._by_id.values())


class TestRunDueRecurring:
    def test_generates_transactions_idempotently(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        transactions = InMemoryTransactionRepository()
        _recurring(recurring, accounts, acct_id)

        first = RunDueRecurring(
            recurring, transactions, FakeUnitOfWork(), FakeClock(TODAY)
        ).execute()
        assert first.generated == 1

        second = RunDueRecurring(
            recurring, transactions, FakeUnitOfWork(), FakeClock(TODAY)
        ).execute()
        assert second.generated == 0  # idempotent: no duplicate on re-run

        # Exactly one transaction was materialised despite two runs.
        materialised = [
            t for t in transactions._by_id.values() if t.recurring_source_id is not None
        ]
        assert len(materialised) == 1

        # The template's next_run advanced to the following month.
        template = recurring.list_for_user(USER)[0]
        assert template.next_run == date(2026, 4, 15)

    def test_skips_inactive(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        dto = _recurring(recurring, accounts, acct_id)
        # Toggle off.
        from recurring.application.use_cases import ToggleRecurring

        ToggleRecurring(recurring, accounts, InMemoryCategoryRepository()).execute(
            USER, dto.id, False
        )
        result = RunDueRecurring(
            recurring, InMemoryTransactionRepository(), FakeUnitOfWork(), FakeClock(TODAY)
        ).execute()
        assert result.generated == 0

    def test_backfills_missed_occurrences_with_their_own_dates(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        transactions = InMemoryTransactionRepository()
        _recurring(recurring, accounts, acct_id, next_run=date(2026, 1, 15))

        result = _run(recurring, transactions)

        assert result.generated == 3
        assert _dates(transactions) == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
        assert recurring.list_for_user(USER)[0].next_run == date(2026, 4, 15)

    def test_month_end_schedule_does_not_drift(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        transactions = InMemoryTransactionRepository()
        _recurring(recurring, accounts, acct_id, next_run=date(2026, 1, 31))

        _run(recurring, transactions, today=date(2026, 3, 31))

        assert _dates(transactions) == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]

    def test_skips_templates_on_archived_accounts(self):
        from finances.application.use_cases import ArchiveAccount

        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository(accounts)
        _recurring(recurring, accounts, acct_id)
        ArchiveAccount(accounts, InMemoryBalanceReader()).execute(USER, acct_id)

        assert _run(recurring, InMemoryTransactionRepository()).generated == 0

    def test_one_failing_template_does_not_block_others(self):
        from shared.exceptions import ConflictError

        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        bad = _recurring(recurring, accounts, acct_id)
        _recurring(recurring, accounts, acct_id, frequency="weekly")
        transactions = InMemoryTransactionRepository()
        original_add = transactions.add

        def add(tx):
            if tx.recurring_source_id == bad.id:
                raise ConflictError
            return original_add(tx)

        transactions.add = add
        result = _run(recurring, transactions)

        assert result.generated == 1
        assert result.skipped == 1


class TestMonthEndSchedule:
    def test_template_on_31st_does_not_drift_across_runs(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        transactions = InMemoryTransactionRepository()
        _recurring(recurring, accounts, acct_id, next_run=date(2026, 1, 31))
        for today in (date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)):
            _run(recurring, transactions, today=today)
        dates = sorted(t.date for t in transactions._by_id.values())
        assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
        (template,) = recurring.list_for_user(USER)
        assert template.next_run == date(2026, 4, 30)


class TestAnchorDate:
    def _create(self, recurring, accounts, acct_id, **fields):
        data = {
            "name": "Аренда",
            "amount_minor": 40000_00,
            "type": "expense",
            "account_id": acct_id,
            "frequency": "monthly",
        } | fields
        return CreateRecurring(
            recurring, accounts, InMemoryCategoryRepository(), FakeClock(TODAY)
        ).execute(USER, CreateRecurringInput.model_validate(data))

    def test_anchor_in_the_past_schedules_the_next_occurrence(self):
        accounts, acct_id = _account()
        dto = self._create(
            InMemoryRecurringTransactionRepository(), accounts, acct_id, anchor_date="2026-01-31"
        )
        assert dto.anchor_date == date(2026, 1, 31)
        assert dto.next_run == date(2026, 3, 31)
        assert dto.account.name == "Счёт"

    def test_anchor_or_next_run_required(self):
        accounts, acct_id = _account()
        with pytest.raises(ValidationError) as exc:
            self._create(InMemoryRecurringTransactionRepository(), accounts, acct_id)
        assert exc.value.errors == {"anchor_date": "required"}

    def test_next_run_alone_is_its_own_anchor(self):
        accounts, acct_id = _account()
        dto = self._create(
            InMemoryRecurringTransactionRepository(), accounts, acct_id, next_run="2026-04-05"
        )
        assert (dto.anchor_date, dto.next_run) == (date(2026, 4, 5), date(2026, 4, 5))

    def test_updating_the_anchor_reschedules(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        dto = self._create(recurring, accounts, acct_id, next_run="2026-04-05")
        updated = UpdateRecurring(
            recurring, accounts, InMemoryCategoryRepository(), FakeClock(TODAY)
        ).execute(USER, dto.id, UpdateRecurringInput(anchor_date=date(2025, 12, 20)))
        assert (updated.anchor_date, updated.next_run) == (date(2025, 12, 20), date(2026, 3, 20))
