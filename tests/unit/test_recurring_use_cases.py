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
    dto = CreateAccount(repo).execute(USER, CreateAccountInput(name="Счёт", type="debit", currency="RUB"))
    return repo, dto.id


def _recurring(recurring_repo, accounts, acct_id, next_run=TODAY):
    return CreateRecurring(recurring_repo, accounts).execute(
        USER,
        CreateRecurringInput(
            name="Аренда", amount_minor=40000_00, type="expense", account_id=acct_id,
            frequency="monthly", next_run=next_run,
        ),
    )


class TestRunDueRecurring:
    def test_generates_transactions_idempotently(self):
        accounts, acct_id = _account()
        recurring = InMemoryRecurringTransactionRepository()
        transactions = InMemoryTransactionRepository()
        _recurring(recurring, accounts, acct_id)

        first = RunDueRecurring(recurring, transactions, accounts, FakeUnitOfWork(), FakeClock(TODAY)).execute()
        assert first.generated == 1

        second = RunDueRecurring(recurring, transactions, accounts, FakeUnitOfWork(), FakeClock(TODAY)).execute()
        assert second.generated == 0  # idempotent: no duplicate on re-run

        # Exactly one transaction was materialised despite two runs.
        materialised = [t for t in transactions._by_id.values() if t.recurring_source_id is not None]
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
        result = RunDueRecurring(recurring, InMemoryTransactionRepository(), accounts, FakeUnitOfWork(), FakeClock(TODAY)).execute()
        assert result.generated == 0
