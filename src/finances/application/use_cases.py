"""Use cases for the finances bounded context (accounts, categories,
transactions, budgets)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from accounts.application.ports import ProfileRepository
from finances.application.currency import CurrencyConverter, base_currency_for
from finances.application.dto import (
    AccountDTO,
    AccountRefDTO,
    BalancePointDTO,
    BudgetDTO,
    CategoryDTO,
    CategoryRefDTO,
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
    FeedPageDTO,
    ListFeedInput,
    ListTransactionsInput,
    TransactionDTO,
    TransactionLabels,
    TransactionPageDTO,
    UpdateAccountInput,
    UpdateBudgetInput,
    UpdateCategoryInput,
    UpdateTransactionInput,
)
from finances.application.ports import (
    AccountRepository,
    BalanceReader,
    BudgetRepository,
    CategoryRepository,
    CurrencyTotals,
    ExchangeRateRepository,
    FeedReader,
    TransactionObserver,
    TransactionRepository,
)
from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import BudgetPeriod, TransactionType
from finances.domain.exceptions import (
    AccountArchivedError,
    AccountNotFoundError,
    BudgetAlreadyExistsError,
    BudgetNotFoundError,
    CategoryCycleError,
    CategoryInUseError,
    CategoryNotFoundError,
    InsufficientFundsError,
    TransactionNotFoundError,
    TransferCurrencyMismatchError,
)
from finances.domain.value_objects import CategoryColor
from shared.application.patch import apply_patch
from shared.application.ports import ExchangeRateProvider
from shared.domain.clock import Clock
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import DEFAULT_CURRENCY, Money
from shared.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Mappers (domain entity → output DTO)
# ---------------------------------------------------------------------------
#: Longest balance history the account chart may ask for.
MAX_HISTORY_WEEKS = 104


def current_balance(account: Account, delta: Decimal | None) -> Money:
    """Initial balance plus every movement of the account."""
    return account.initial_balance + Money(delta or Decimal(0), account.currency.value)


def _account_dto(a: Account, delta: Decimal | None = None) -> AccountDTO:
    return AccountDTO(
        id=a.id,
        name=a.name,
        type=a.type,
        currency=a.currency.value,
        initial_balance=a.initial_balance,
        color=a.color.value,
        last4=a.last4,
        credit_limit=a.credit_limit,
        interest_rate=a.interest_rate,
        is_archived=a.is_archived,
        balance=current_balance(a, delta),
    )


def _category_dto(c: Category, transaction_count: int = 0) -> CategoryDTO:
    return CategoryDTO(
        id=c.id,
        name=c.name,
        type=c.type,
        icon=c.icon,
        color=c.color.value,
        parent_id=c.parent_id,
        is_system=c.is_system,
        transaction_count=transaction_count,
    )


def account_refs(accounts: AccountRepository, user_id: UUID) -> dict[UUID, AccountRefDTO]:
    """``{id, name, color}`` of every account of the user, archived ones included."""
    return {
        a.id: AccountRefDTO(id=a.id, name=a.name, color=a.color.value)
        for a in accounts.list_for_user(user_id, include_archived=True)
    }


def require_funds(balances: BalanceReader, account: Account, amount: Money, field: str) -> None:
    """Raise :class:`InsufficientFundsError` when ``amount`` exceeds the current balance."""
    delta = balances.deltas(account.user_id, [account.id]).get(account.id)
    if amount > current_balance(account, delta):
        raise InsufficientFundsError(field=field)


def category_ref(c: Category) -> CategoryRefDTO:
    return CategoryRefDTO(id=c.id, name=c.name, icon=c.icon, color=c.color.value)


def _transaction_dto(t: Transaction, labels: TransactionLabels | None = None) -> TransactionDTO:
    return TransactionDTO(
        id=t.id,
        account_id=t.account_id,
        category_id=t.category_id,
        type=t.type,
        amount=t.amount,
        date=t.date,
        time=t.time,
        note=t.note,
        title=t.title,
        receipt_id=t.receipt_id,
        transfer_to_account_id=t.transfer_to_account_id,
        labels=labels,
    )


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
class CreateAccount:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    def execute(self, user_id: UUID, data: CreateAccountInput) -> AccountDTO:
        currency = CurrencyCode(data.currency)
        account = Account(
            user_id=user_id,
            name=data.name,
            type=data.type,
            currency=currency,
            initial_balance=Money.from_minor_units(data.initial_balance_minor, data.currency),
            color=CategoryColor(data.color),
            last4=data.last4,
            credit_limit=(
                Money.from_minor_units(data.credit_limit_minor, data.currency)
                if data.credit_limit_minor is not None
                else None
            ),
            interest_rate=data.interest_rate,
        )
        return _account_dto(self._accounts.add(account))


class UpdateAccount:
    def __init__(self, accounts: AccountRepository, balances: BalanceReader) -> None:
        self._accounts = accounts
        self._balances = balances

    def execute(self, user_id: UUID, account_id: UUID, data: UpdateAccountInput) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        currency = account.currency.value
        delta = self._balances.deltas(user_id, [account_id]).get(account_id)
        updated = apply_patch(
            account,
            data,
            fields={
                "color": ("color", CategoryColor),
                "credit_limit_minor": (
                    "credit_limit",
                    lambda minor: Money.from_minor_units(minor, currency),
                ),
                # The movements stay as they are; the starting point moves instead.
                "balance_minor": (
                    "initial_balance",
                    lambda minor: (
                        Money.from_minor_units(minor, currency)
                        - Money(delta or Decimal(0), currency)
                    ),
                ),
            },
            nullable={"last4", "credit_limit_minor"},
        )
        return _account_dto(self._accounts.update(updated), delta)


class _SetArchived:
    archived: bool

    def __init__(self, accounts: AccountRepository, balances: BalanceReader) -> None:
        self._accounts = accounts
        self._balances = balances

    def execute(self, user_id: UUID, account_id: UUID) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        saved = self._accounts.update(replace(account, is_archived=self.archived))
        return _account_dto(saved, self._balances.deltas(user_id, [account_id]).get(account_id))


class ArchiveAccount(_SetArchived):
    archived = True


class UnarchiveAccount(_SetArchived):
    archived = False


class ListAccounts:
    def __init__(self, accounts: AccountRepository, balances: BalanceReader) -> None:
        self._accounts = accounts
        self._balances = balances

    def execute(self, user_id: UUID, *, include_archived: bool = False) -> list[AccountDTO]:
        accounts = self._accounts.list_for_user(user_id, include_archived=include_archived)
        deltas = self._balances.deltas(user_id, [a.id for a in accounts])
        return [_account_dto(a, deltas.get(a.id)) for a in accounts]


class GetAccountDetail:
    def __init__(self, accounts: AccountRepository, balances: BalanceReader) -> None:
        self._accounts = accounts
        self._balances = balances

    def execute(self, user_id: UUID, account_id: UUID) -> AccountDTO:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        return _account_dto(account, self._balances.deltas(user_id, [account_id]).get(account_id))


class GetBalanceHistory:
    """Balance before the window, after every day with movements, and today, ascending."""

    def __init__(self, accounts: AccountRepository, balances: BalanceReader, clock: Clock) -> None:
        self._accounts = accounts
        self._balances = balances
        self._clock = clock

    def execute(self, user_id: UUID, account_id: UUID, weeks: int = 6) -> list[BalancePointDTO]:
        if not 1 <= weeks <= MAX_HISTORY_WEEKS:
            msg = f"weeks must be within 1..{MAX_HISTORY_WEEKS}."
            raise ValidationError(msg, field="weeks", field_code="invalid")
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        today = self._clock.now().date()
        start = today - timedelta(weeks=weeks)
        currency = account.currency.value
        before = self._balances.deltas(user_id, [account_id], before=start).get(account_id)
        balance = current_balance(account, before)
        points = [BalancePointDTO(at=start, balance=balance)]
        daily = self._balances.daily_deltas(user_id, account_id, start, today)
        for day in sorted(daily):
            balance = balance + Money(daily[day], currency)
            points.append(BalancePointDTO(at=day, balance=balance))
        if points[-1].at != today:
            points.append(BalancePointDTO(at=today, balance=balance))
        return points


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
class ListCategories:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID) -> list[CategoryDTO]:
        counts = self._categories.transaction_counts(user_id)
        return [
            _category_dto(c, counts.get(c.id, 0)) for c in self._categories.list_for_user(user_id)
        ]


class CreateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID, data: CreateCategoryInput) -> CategoryDTO:
        if data.parent_id is not None:
            parent = self._categories.get_by_id(data.parent_id, user_id)
            if parent is None:
                raise CategoryNotFoundError(data.parent_id)
        category = Category(
            user_id=user_id,
            name=data.name,
            type=data.type,
            icon=data.icon,
            color=CategoryColor(data.color),
            parent_id=data.parent_id,
        )
        return _category_dto(self._categories.add(category))


class UpdateCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID, category_id: UUID, data: UpdateCategoryInput) -> CategoryDTO:
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if category.is_system:
            raise CategoryInUseError("System categories are read-only.")
        if data.parent_id is not None and data.parent_id != category.parent_id:
            if data.parent_id == category_id:
                raise CategoryCycleError
            if self._categories.get_by_id(data.parent_id, user_id) is None:
                raise CategoryNotFoundError(data.parent_id)
            if self._categories.is_ancestor(user_id, category_id, data.parent_id):
                raise CategoryCycleError
        updated = apply_patch(
            category, data, fields={"color": ("color", CategoryColor)}, nullable={"parent_id"}
        )
        return _category_dto(self._categories.update(updated))


class DeleteCategory:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    def execute(self, user_id: UUID, category_id: UUID) -> None:
        category = self._categories.get_by_id(category_id, user_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        if category.is_system:
            raise CategoryInUseError("System categories cannot be deleted.")
        if self._categories.has_transactions(category_id, user_id):
            raise CategoryInUseError
        if self._categories.has_budgets(category_id, user_id):
            raise CategoryInUseError("The category has budgets; delete them first.")
        self._categories.delete(category_id, user_id)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
def require_category(
    categories: CategoryRepository,
    user_id: UUID,
    category_id: UUID | None,
    tx_type: TransactionType,
) -> None:
    """Check that ``category_id`` (if any) is the user's and fits ``tx_type``."""
    if category_id is None:
        return
    category = categories.get_by_id(category_id, user_id)
    if category is None:
        raise CategoryNotFoundError(category_id)
    if tx_type in (TransactionType.EXPENSE, TransactionType.INCOME) and category.type != tx_type:
        msg = (
            f"Category type {category.type.value} does not match transaction type {tx_type.value}."
        )
        raise ValidationError(msg)


class _TransactionGuard:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
    ) -> None:
        self._accounts = accounts
        self._categories = categories
        self._transactions = transactions

    def _require_account(
        self, user_id: UUID, account_id: UUID, *, allow_archived: bool = False
    ) -> Account:
        account = self._accounts.get_by_id(account_id, user_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        if account.is_archived and not allow_archived:
            raise AccountArchivedError
        return account

    def validate(
        self,
        user_id: UUID,
        *,
        account_id: UUID,
        tx_type: TransactionType,
        category_id: UUID | None,
        transfer_to_account_id: UUID | None,
    ) -> Account:
        """Check references and return the (source) account."""
        account = self._require_account(user_id, account_id)
        if tx_type is TransactionType.TRANSFER and transfer_to_account_id not in (None, account_id):
            dest = self._require_account(user_id, transfer_to_account_id)
            if dest.currency != account.currency:
                raise TransferCurrencyMismatchError
        # A missing or identical destination is rejected by the Transaction entity.
        require_category(self._categories, user_id, category_id, tx_type)
        return account


class CreateTransaction:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
        observer: TransactionObserver | None = None,
    ) -> None:
        self._guard = _TransactionGuard(accounts, categories, transactions)
        self._transactions = transactions
        self._observer = observer

    def execute(self, user_id: UUID, data: CreateTransactionInput) -> TransactionDTO:
        account = self._guard.validate(
            user_id,
            account_id=data.account_id,
            tx_type=data.type,
            category_id=data.category_id,
            transfer_to_account_id=data.transfer_to_account_id,
        )
        transaction = Transaction(
            user_id=user_id,
            account_id=data.account_id,
            category_id=data.category_id,
            type=data.type,
            amount=Money.from_minor_units(data.amount_minor, account.currency.value),
            date=data.date,
            time=data.time,
            note=data.note,
            title=data.title.strip(),
            transfer_to_account_id=data.transfer_to_account_id,
        )
        saved = self._transactions.add(transaction)
        if self._observer is not None:
            self._observer.changed(user_id, None, saved)
        return _transaction_dto(saved)


class GetTransaction:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, transaction_id: UUID) -> TransactionDTO:
        found = self._transactions.get_labeled(transaction_id, user_id)
        if found is None:
            raise TransactionNotFoundError(transaction_id)
        return _transaction_dto(*found)


class UpdateTransaction:
    def __init__(
        self,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionRepository,
        observer: TransactionObserver | None = None,
    ) -> None:
        self._guard = _TransactionGuard(accounts, categories, transactions)
        self._transactions = transactions
        self._observer = observer

    def execute(
        self, user_id: UUID, transaction_id: UUID, data: UpdateTransactionInput
    ) -> TransactionDTO:
        tx = self._transactions.get_by_id(transaction_id, user_id)
        if tx is None:
            raise TransactionNotFoundError(transaction_id)
        # The amount is re-denominated below, once the (possibly new) account is known.
        draft = apply_patch(
            tx,
            data,
            fields={
                "amount_minor": ("amount", lambda _: tx.amount),
                "title": ("title", str.strip),
            },
            nullable={"category_id", "time", "transfer_to_account_id"},
        )
        account = self._guard.validate(
            user_id,
            account_id=draft.account_id,
            tx_type=draft.type,
            category_id=draft.category_id,
            transfer_to_account_id=draft.transfer_to_account_id,
        )
        minor = tx.amount.to_minor_units() if data.amount_minor is None else data.amount_minor
        updated = replace(draft, amount=Money.from_minor_units(minor, account.currency.value))
        saved = self._transactions.update(updated)
        if self._observer is not None:
            self._observer.changed(user_id, tx, saved)
        return _transaction_dto(saved)


class DeleteTransaction:
    def __init__(
        self, transactions: TransactionRepository, observer: TransactionObserver | None = None
    ) -> None:
        self._transactions = transactions
        self._observer = observer

    def execute(self, user_id: UUID, transaction_id: UUID) -> None:
        before = self._transactions.get_by_id(transaction_id, user_id)
        if before is None or not self._transactions.delete(transaction_id, user_id):
            raise TransactionNotFoundError(transaction_id)
        if self._observer is not None:
            self._observer.changed(user_id, before, None)


class ListFeed:
    """Transactions with goal contributions and debt openings/repayments, newest first."""

    def __init__(self, feed: FeedReader) -> None:
        self._feed = feed

    def execute(self, user_id: UUID, data: ListFeedInput) -> FeedPageDTO:
        return self._feed.page(
            user_id,
            account_id=data.account_id,
            date_from=data.date_from,
            date_to=data.date_to,
            cursor=data.cursor,
            limit=data.limit,
        )


class ListTransactions:
    def __init__(self, transactions: TransactionRepository) -> None:
        self._transactions = transactions

    def execute(self, user_id: UUID, data: ListTransactionsInput) -> TransactionPageDTO:
        items, next_cursor = self._transactions.list_for_user(
            user_id,
            account_id=data.account_id,
            category_id=data.category_id,
            type=data.type,
            date_from=data.date_from,
            date_to=data.date_to,
            search=data.search,
            cursor=data.cursor,
            limit=data.limit,
        )
        return TransactionPageDTO(
            items=[_transaction_dto(t, labels) for t, labels in items],
            next_cursor=next_cursor,
        )


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------
def descendant_ids(categories: Iterable[Category], root_id: UUID) -> set[UUID]:
    """``root_id`` and every category below it."""
    children: dict[UUID, list[UUID]] = {}
    for c in categories:
        if c.parent_id is not None:
            children.setdefault(c.parent_id, []).append(c.id)
    result: set[UUID] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, ()))
    return result


def merge_totals(totals: Iterable[CurrencyTotals | None]) -> CurrencyTotals:
    merged: CurrencyTotals = {}
    for bucket in totals:
        for currency, money in (bucket or {}).items():
            merged[currency] = merged.get(currency, Money.zero(currency)) + money
    return merged


class BudgetReporter:
    """Renders budgets with their current period and the spending in it.

    Spending counts expenses of the budget's category and all its subcategories;
    one aggregate query per distinct period. The limit and the spending are in
    the profile's base currency, or in the budget's own one when no rate
    converts it.
    """

    def __init__(
        self,
        transactions: TransactionRepository,
        categories: CategoryRepository,
        rates: ExchangeRateRepository,
        clock: Clock,
        profiles: ProfileRepository | None = None,
    ) -> None:
        self._transactions = transactions
        self._categories = categories
        self._rates = rates
        self._clock = clock
        self._profiles = profiles

    def report(self, user_id: UUID, budgets: list[Budget]) -> list[BudgetDTO]:
        if not budgets:
            return []
        today = self._clock.now().date()
        categories = self._categories.list_for_user(user_id)
        by_id = {c.id: c for c in categories}
        bounds = {b.id: b.period_bounds(today) for b in budgets}
        spent_by_window = {
            window: self._transactions.sum_by_category(
                user_id, type=TransactionType.EXPENSE, date_from=window[0], date_to=window[1]
            )
            for window in set(bounds.values())
        }
        base = base_currency_for(self._profiles, user_id) if self._profiles else None
        converters: dict[str, CurrencyConverter] = {}
        result = []
        for budget in budgets:
            currency = budget.amount.currency
            if base is not None:
                to_base = converters.setdefault(base, CurrencyConverter(self._rates, base))
                if to_base.can_convert(currency):
                    currency = base
            fx = converters.setdefault(currency, CurrencyConverter(self._rates, currency))
            window = spent_by_window[bounds[budget.id]]
            ids = descendant_ids(categories, budget.category_id)
            category = by_id.get(budget.category_id)
            result.append(
                BudgetDTO(
                    id=budget.id,
                    category=category_ref(category)
                    if category
                    else CategoryRefDTO(
                        id=budget.category_id, name="", icon="tag", color="default"
                    ),
                    amount=fx.total({budget.amount.currency: budget.amount}),
                    period=budget.period,
                    start_date=budget.start_date,
                    end_date=budget.end_date,
                    is_active=budget.is_active,
                    period_start=bounds[budget.id][0],
                    period_end=bounds[budget.id][1],
                    spent=fx.total(merge_totals(window.get(i) for i in ids)),
                )
            )
        return result

    def report_one(self, user_id: UUID, budget: Budget) -> BudgetDTO:
        return self.report(user_id, [budget])[0]


def _check_budget(
    budgets: BudgetRepository,
    categories: CategoryRepository,
    budget: Budget,
    *,
    exclude_id: UUID | None = None,
) -> None:
    category = categories.get_by_id(budget.category_id, budget.user_id)
    if category is None:
        raise CategoryNotFoundError(budget.category_id)
    if category.type is not TransactionType.EXPENSE:
        msg = "A budget can only target an expense category."
        raise ValidationError(msg, field="category_id", field_code="invalid")
    if budget.period is BudgetPeriod.ONE_TIME:
        for name in ("start_date", "end_date"):
            if getattr(budget, name) is None:
                msg = f"A one-time budget requires {name}."
                raise ValidationError(msg, field=name, field_code="required")
    if budgets.exists_for_category(budget.user_id, budget.category_id, exclude_id=exclude_id):
        raise BudgetAlreadyExistsError


class CreateBudget:
    def __init__(
        self,
        budgets: BudgetRepository,
        categories: CategoryRepository,
        profiles: ProfileRepository,
        reporter: BudgetReporter,
    ) -> None:
        self._budgets = budgets
        self._categories = categories
        self._profiles = profiles
        self._reporter = reporter

    def execute(self, user_id: UUID, data: CreateBudgetInput) -> BudgetDTO:
        # Budgets are denominated in the user's base currency.
        profile = self._profiles.get_by_user(user_id)
        currency = profile.base_currency.value if profile else DEFAULT_CURRENCY
        budget = Budget(
            user_id=user_id,
            category_id=data.category_id,
            amount=Money.from_minor_units(data.amount_minor, currency),
            period=data.period,
            start_date=data.start_date,
            end_date=data.end_date,
            is_active=data.is_active,
        )
        _check_budget(self._budgets, self._categories, budget)
        return self._reporter.report_one(user_id, self._budgets.add(budget))


class UpdateBudget:
    def __init__(
        self,
        budgets: BudgetRepository,
        categories: CategoryRepository,
        reporter: BudgetReporter,
        profiles: ProfileRepository | None = None,
    ) -> None:
        self._budgets = budgets
        self._categories = categories
        self._reporter = reporter
        self._profiles = profiles

    def execute(self, user_id: UUID, budget_id: UUID, data: UpdateBudgetInput) -> BudgetDTO:
        budget = self._budgets.get_by_id(budget_id, user_id)
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        # A new limit is entered in the base currency, like a new budget.
        currency = (
            base_currency_for(self._profiles, user_id)
            if self._profiles is not None
            else budget.amount.currency
        )
        updated = apply_patch(
            budget,
            data,
            fields={"amount_minor": ("amount", lambda m: Money.from_minor_units(m, currency))},
            nullable={"start_date", "end_date"},
        )
        _check_budget(self._budgets, self._categories, updated, exclude_id=budget_id)
        return self._reporter.report_one(user_id, self._budgets.update(updated))


class ListBudgets:
    def __init__(self, budgets: BudgetRepository, reporter: BudgetReporter) -> None:
        self._budgets = budgets
        self._reporter = reporter

    def execute(self, user_id: UUID) -> list[BudgetDTO]:
        return self._reporter.report(user_id, self._budgets.list_for_user(user_id))


class GetBudgetDetail:
    def __init__(self, budgets: BudgetRepository, reporter: BudgetReporter) -> None:
        self._budgets = budgets
        self._reporter = reporter

    def execute(self, user_id: UUID, budget_id: UUID) -> BudgetDTO:
        budget = self._budgets.get_by_id(budget_id, user_id)
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        return self._reporter.report_one(user_id, budget)


class DeleteBudget:
    def __init__(self, budgets: BudgetRepository) -> None:
        self._budgets = budgets

    def execute(self, user_id: UUID, budget_id: UUID) -> None:
        if not self._budgets.delete(budget_id, user_id):
            raise BudgetNotFoundError(budget_id)


# ---------------------------------------------------------------------------
# Exchange rates
# ---------------------------------------------------------------------------
class RefreshExchangeRates:
    """Store the provider's latest rates against ``base`` (idempotent per day)."""

    def __init__(
        self, provider: ExchangeRateProvider, rates: ExchangeRateRepository, base: str
    ) -> None:
        self._provider = provider
        self._rates = rates
        self._base = base

    def execute(self) -> int:
        snapshot = self._provider.latest(CurrencyCode(self._base))
        base = CurrencyCode(snapshot.base)
        return self._rates.save_many(
            [
                ExchangeRate(base=base, target=CurrencyCode(code), rate=rate, date=snapshot.date)
                for code, rate in sorted(snapshot.rates.items())
            ]
        )
