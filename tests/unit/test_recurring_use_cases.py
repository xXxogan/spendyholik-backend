from datetime import date
from uuid import uuid4

from finances.application.dto import CreateAccountInput
from finances.application.use_cases import CreateAccount
from recurring.application.dto import CreateRecurringInput
from recurring.application.use_cases import CreateRecurring, RunDueRecurring
from tests.fakes import (
    FakeClock,
    FakeUnitOfWork,
    InMemoryAccountRepository,
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
    return CreateRecurring(recurring_repo, accounts).execute(
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

        ToggleRecurring(recurring).execute(USER, dto.id, False)
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
        ArchiveAccount(accounts).execute(USER, acct_id)

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
