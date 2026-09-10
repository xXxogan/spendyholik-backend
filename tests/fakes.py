"""In-memory fake implementations of the application ports, for unit tests."""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from accounts.application.ports import (
    AuthTokenService,
    PasswordHasher,
    PasswordResetGateway,
    ProfileRepository,
    SocialIdentity,
    SocialIdentityProvider,
    TokenPair,
    UserRepository,
)
from accounts.domain.entities import Profile, User
from accounts.domain.value_objects import Email
from finances.application.ports import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    ExchangeRateRepository,
    TransactionRepository,
)
from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import TransactionType
from shared.application.ports import ExchangeRateProvider, UnitOfWork
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money


class FakeUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.committed = False


class FakePasswordHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"hashed:{password}"


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, User] = {}
        self._password_hashes: dict[UUID, str] = {}

    def add(self, user: User, password_hash: str) -> User:
        self._by_id[user.id] = user
        self._password_hashes[user.id] = password_hash
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        return self._by_id.get(user_id)

    def get_by_email(self, email: Email) -> User | None:
        for user in self._by_id.values():
            if user.email == email:
                return user
        return None

    def email_exists(self, email: Email) -> bool:
        return self.get_by_email(email) is not None

    def update(self, user: User) -> User:
        self._by_id[user.id] = user
        return user

    def get_password_hash(self, user_id: UUID) -> str | None:
        return self._password_hashes.get(user_id)

    def set_password(self, user_id: UUID, password_hash: str) -> None:
        self._password_hashes[user_id] = password_hash


class InMemoryProfileRepository(ProfileRepository):
    def __init__(self) -> None:
        self._by_user: dict[UUID, Profile] = {}

    def add(self, profile: Profile) -> Profile:
        self._by_user[profile.user_id] = profile
        return profile

    def get_by_user(self, user_id: UUID) -> Profile | None:
        return self._by_user.get(user_id)

    def update(self, profile: Profile) -> Profile:
        self._by_user[profile.user_id] = profile
        return profile


class FakeAuthTokenService(AuthTokenService):
    def __init__(self) -> None:
        self._revoked: set[str] = set()

    def issue(self, user: User) -> TokenPair:
        now = datetime.now(timezone.utc)
        return TokenPair(
            access=f"access-{user.id}",
            refresh=f"refresh-{user.id}-{now.timestamp()}",
            access_expires_at=now + timedelta(minutes=15),
            refresh_expires_at=now + timedelta(days=30),
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        if refresh_token in self._revoked:
            msg = "Refresh token revoked"
            raise ValueError(msg)
        user_id = refresh_token.split("-")[1]
        now = datetime.now(timezone.utc)
        return TokenPair(
            access=f"access-{user_id}",
            refresh=f"refresh-{user_id}-{now.timestamp()}",
            access_expires_at=now + timedelta(minutes=15),
            refresh_expires_at=now + timedelta(days=30),
        )

    def revoke(self, refresh_token: str) -> None:
        self._revoked.add(refresh_token)


class FakePasswordResetGateway(PasswordResetGateway):
    def __init__(self) -> None:
        self._tokens: dict[str, UUID] = {}

    def issue_token(self, user: User) -> str:
        token = secrets.token_urlsafe(16)
        self._tokens[token] = user.id
        return token

    def resolve_token(self, token: str) -> UUID | None:
        return self._tokens.get(token)

    def invalidate_token(self, token: str) -> None:
        self._tokens.pop(token, None)


class FakeSocialIdentityProvider(SocialIdentityProvider):
    def __init__(self, identities: dict[str, SocialIdentity] | None = None) -> None:
        self._identities = identities or {}

    def exchange(self, provider: str, credential: str) -> SocialIdentity | None:
        return self._identities.get(f"{provider}:{credential}")


class InMemoryAccountRepository(AccountRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Account] = {}

    def add(self, account: Account) -> Account:
        self._by_id[account.id] = account
        return account

    def get_by_id(self, account_id: UUID, user_id: UUID) -> Account | None:
        account = self._by_id.get(account_id)
        if account is None or account.user_id != user_id:
            return None
        return account

    def list_for_user(self, user_id: UUID, *, include_archived: bool = False) -> list[Account]:
        result = [a for a in self._by_id.values() if a.user_id == user_id]
        if not include_archived:
            result = [a for a in result if not a.is_archived]
        return result

    def update(self, account: Account) -> Account:
        self._by_id[account.id] = account
        return account

    def delete(self, account_id: UUID, user_id: UUID) -> None:
        self._by_id.pop(account_id, None)


class InMemoryCategoryRepository(CategoryRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Category] = {}

    def add(self, category: Category) -> Category:
        self._by_id[category.id] = category
        return category

    def get_by_id(self, category_id: UUID, user_id: UUID) -> Category | None:
        category = self._by_id.get(category_id)
        if category is None or category.user_id != user_id:
            return None
        return category

    def list_for_user(self, user_id: UUID) -> list[Category]:
        return [c for c in self._by_id.values() if c.user_id == user_id]

    def update(self, category: Category) -> Category:
        self._by_id[category.id] = category
        return category

    def delete(self, category_id: UUID, user_id: UUID) -> None:
        self._by_id.pop(category_id, None)

    def is_ancestor(self, user_id: UUID, ancestor_id: UUID, descendant_id: UUID) -> bool:
        current = self._by_id.get(descendant_id)
        seen: set[UUID] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.id == ancestor_id:
                return True
            if current.parent_id is None:
                return False
            current = self._by_id.get(current.parent_id)
        return False

    def has_transactions(self, category_id: UUID, user_id: UUID) -> bool:
        return False  # overridden by tests that need it


class InMemoryTransactionRepository(TransactionRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Transaction] = {}
        self._category_usage: set[UUID] = set()

    def add(self, transaction: Transaction) -> Transaction:
        self._by_id[transaction.id] = transaction
        if transaction.category_id is not None:
            self._category_usage.add(transaction.category_id)
        return transaction

    def get_by_id(self, transaction_id: UUID, user_id: UUID) -> Transaction | None:
        tx = self._by_id.get(transaction_id)
        if tx is None or tx.user_id != user_id:
            return None
        return tx

    def update(self, transaction: Transaction) -> Transaction:
        self._by_id[transaction.id] = transaction
        return transaction

    def delete(self, transaction_id: UUID, user_id: UUID) -> None:
        self._by_id.pop(transaction_id, None)

    def list_for_user(self, user_id, *, account_id=None, category_id=None, type=None,
                      date_from=None, date_to=None, search=None, cursor=None, limit=20):
        items = [t for t in self._by_id.values() if t.user_id == user_id]
        if account_id is not None:
            items = [t for t in items if t.account_id == account_id]
        if category_id is not None:
            items = [t for t in items if t.category_id == category_id]
        if type is not None:
            items = [t for t in items if t.type is type]
        if date_from is not None:
            items = [t for t in items if t.date >= date_from]
        if date_to is not None:
            items = [t for t in items if t.date <= date_to]
        if search is not None:
            items = [t for t in items if search.lower() in t.note.lower()]
        items.sort(key=lambda t: (t.date, str(t.id)), reverse=True)
        if cursor is not None:
            items = [t for t in items if f"{t.date}_{t.id}" < cursor]
        page = items[:limit]
        next_cursor = f"{page[-1].date}_{page[-1].id}" if len(items) > limit else None
        return page, next_cursor

    def total_amount(self, user_id, *, type=None, account_id=None, category_id=None,
                     date_from=None, date_to=None):
        items = [t for t in self._by_id.values() if t.user_id == user_id]
        if type is not None:
            items = [t for t in items if t.type is type]
        if account_id is not None:
            items = [t for t in items if t.account_id == account_id]
        if category_id is not None:
            items = [t for t in items if t.category_id == category_id]
        if date_from is not None:
            items = [t for t in items if t.date >= date_from]
        if date_to is not None:
            items = [t for t in items if t.date <= date_to]
        if not items:
            return None
        currency = items[0].amount.currency
        return sum((t.amount for t in items), Money.zero(currency))

    def category_is_used(self, category_id: UUID) -> bool:
        return category_id in self._category_usage


class InMemoryBudgetRepository(BudgetRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Budget] = {}

    def add(self, budget: Budget) -> Budget:
        self._by_id[budget.id] = budget
        return budget

    def get_by_id(self, budget_id: UUID, user_id: UUID) -> Budget | None:
        budget = self._by_id.get(budget_id)
        if budget is None or budget.user_id != user_id:
            return None
        return budget

    def list_for_user(self, user_id: UUID) -> list[Budget]:
        return [b for b in self._by_id.values() if b.user_id == user_id]

    def update(self, budget: Budget) -> Budget:
        self._by_id[budget.id] = budget
        return budget

    def delete(self, budget_id: UUID, user_id: UUID) -> None:
        self._by_id.pop(budget_id, None)


class InMemoryExchangeRateRepository(ExchangeRateRepository):
    def __init__(self) -> None:
        self._rates: list[ExchangeRate] = []

    def add(self, rate: ExchangeRate) -> ExchangeRate:
        self._rates.append(rate)
        return rate

    def get_latest(self, base: CurrencyCode, target: CurrencyCode) -> ExchangeRate | None:
        for rate in reversed(self._rates):
            if rate.base == base and rate.target == target:
                return rate
        return None


class StubExchangeRateProvider(ExchangeRateProvider):
    def __init__(self, rates: dict[tuple[str, str], "object"] | None = None) -> None:
        self._rates = rates or {}

    def get_rate(self, base, target, on=None):
        return self._rates.get((base.value, target.value))
