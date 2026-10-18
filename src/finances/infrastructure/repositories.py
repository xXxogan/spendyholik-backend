"""Django ORM implementations of the finances ports."""

from __future__ import annotations

import base64
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError, models
from django.db.models import Sum
from django.db.models.functions import TruncMonth

from finances.application.dto import TransactionLabels
from finances.application.ports import (
    AccountRepository,
    BudgetRepository,
    CategoryRepository,
    ExchangeRateRepository,
    TransactionRepository,
)
from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import TransactionType
from finances.infrastructure.mappers import (
    account_to_domain,
    account_to_orm,
    budget_to_domain,
    budget_to_orm,
    category_to_domain,
    category_to_orm,
    exchange_rate_to_domain,
    exchange_rate_to_orm,
    transaction_to_domain,
    transaction_to_orm,
)
from finances.infrastructure.orm.models import (
    Account as AccountORM,
)
from finances.infrastructure.orm.models import (
    Budget as BudgetORM,
)
from finances.infrastructure.orm.models import (
    Category as CategoryORM,
)
from finances.infrastructure.orm.models import (
    ExchangeRate as ExchangeRateORM,
)
from finances.infrastructure.orm.models import (
    Transaction as TransactionORM,
)
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import Money
from shared.exceptions import ConflictError, ValidationError


def _encode_cursor(tx: TransactionORM) -> str:
    raw = f"{tx.date.isoformat()}|{tx.created_at.isoformat()}|{tx.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, datetime, UUID]:
    try:
        day, created_at, pk = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return date.fromisoformat(day), datetime.fromisoformat(created_at), UUID(pk)
    except (ValueError, UnicodeDecodeError) as exc:
        msg = "Invalid cursor."
        raise ValidationError(msg) from exc


def _labels(tx: TransactionORM) -> TransactionLabels:
    category = tx.category
    return TransactionLabels(
        account_name=tx.account.name,
        category_name=category.name if category else None,
        category_icon=category.icon if category else None,
        category_color=category.color if category else None,
    )


def _group_by_currency(rows, key) -> dict:
    """Fold ``values(..., "account__currency").annotate(total=...)`` rows into
    ``{key(row): {currency: Money}}``."""
    result: dict = {}
    for row in rows:
        currency = row["account__currency"]
        result.setdefault(key(row), {})[currency] = Money(Decimal(row["total"]), currency)
    return result


_TRANSACTION_UPDATE_FIELDS = (
    "account_id",
    "category_id",
    "type",
    "amount",
    "date",
    "time",
    "note",
    "receipt_id",
    "transfer_to_account_id",
    "recurring_source_id",
)


class DjangoAccountRepository(AccountRepository):
    def add(self, account: Account) -> Account:
        account_to_orm(account).save(force_insert=True)
        return account

    def get_by_id(self, account_id: UUID, user_id: UUID) -> Account | None:
        orm = AccountORM.objects.filter(pk=account_id, user_id=user_id).first()
        return account_to_domain(orm) if orm else None

    def list_for_user(self, user_id: UUID, *, include_archived: bool = False) -> list[Account]:
        qs = AccountORM.objects.filter(user_id=user_id)
        if not include_archived:
            qs = qs.filter(is_archived=False)
        return [account_to_domain(a) for a in qs]

    def update(self, account: Account) -> Account:
        AccountORM.objects.filter(pk=account.id, user_id=account.user_id).update(
            name=account.name,
            type=account.type.value,
            color=account.color.value,
            last4=account.last4,
            credit_limit=account.credit_limit.amount if account.credit_limit is not None else None,
            interest_rate=account.interest_rate,
            is_archived=account.is_archived,
        )
        return account

    def delete(self, account_id: UUID, user_id: UUID) -> bool:
        deleted, _ = AccountORM.objects.filter(pk=account_id, user_id=user_id).delete()
        return deleted > 0


class DjangoCategoryRepository(CategoryRepository):
    def add(self, category: Category) -> Category:
        category_to_orm(category).save(force_insert=True)
        return category

    def get_by_id(self, category_id: UUID, user_id: UUID) -> Category | None:
        orm = CategoryORM.objects.filter(pk=category_id, user_id=user_id).first()
        return category_to_domain(orm) if orm else None

    def list_for_user(self, user_id: UUID) -> list[Category]:
        return [category_to_domain(c) for c in CategoryORM.objects.filter(user_id=user_id)]

    def update(self, category: Category) -> Category:
        CategoryORM.objects.filter(pk=category.id, user_id=category.user_id).update(
            name=category.name,
            icon=category.icon,
            color=category.color.value,
            parent_id=category.parent_id,
        )
        return category

    def delete(self, category_id: UUID, user_id: UUID) -> bool:
        deleted, _ = CategoryORM.objects.filter(pk=category_id, user_id=user_id).delete()
        return deleted > 0

    def is_ancestor(self, user_id: UUID, ancestor_id: UUID, descendant_id: UUID) -> bool:
        current = CategoryORM.objects.filter(pk=descendant_id, user_id=user_id).first()
        seen: set[UUID] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.id == ancestor_id:
                return True
            current = current.parent
        return False

    def has_transactions(self, category_id: UUID, user_id: UUID) -> bool:
        return TransactionORM.objects.filter(category_id=category_id, user_id=user_id).exists()


class DjangoTransactionRepository(TransactionRepository):
    def add(self, transaction: Transaction) -> Transaction:
        try:
            transaction_to_orm(transaction).save(force_insert=True)
        except IntegrityError as exc:
            msg = "Transaction already exists."
            raise ConflictError(msg) from exc
        return transaction

    def get_by_id(self, transaction_id: UUID, user_id: UUID) -> Transaction | None:
        orm = (
            TransactionORM.objects.filter(pk=transaction_id, user_id=user_id)
            .select_related("account")
            .first()
        )
        return transaction_to_domain(orm) if orm else None

    def get_labeled(self, transaction_id, user_id):
        orm = (
            TransactionORM.objects.filter(pk=transaction_id, user_id=user_id)
            .select_related("account", "category")
            .first()
        )
        return (transaction_to_domain(orm), _labels(orm)) if orm else None

    def update(self, transaction: Transaction) -> Transaction:
        fresh = transaction_to_orm(transaction)
        TransactionORM.objects.filter(pk=transaction.id, user_id=transaction.user_id).update(
            **{field: getattr(fresh, field) for field in _TRANSACTION_UPDATE_FIELDS}
        )
        return transaction

    def delete(self, transaction_id: UUID, user_id: UUID) -> bool:
        deleted, _ = TransactionORM.objects.filter(pk=transaction_id, user_id=user_id).delete()
        return deleted > 0

    def list_for_user(
        self,
        user_id,
        *,
        account_id=None,
        category_id=None,
        type=None,
        date_from=None,
        date_to=None,
        search=None,
        cursor=None,
        limit=20,
    ):
        qs = TransactionORM.objects.filter(user_id=user_id).select_related("account", "category")
        if account_id is not None:
            qs = qs.filter(account_id=account_id)
        if category_id is not None:
            qs = qs.filter(category_id=category_id)
        if type is not None:
            qs = qs.filter(type=type.value)
        if date_from is not None:
            qs = qs.filter(date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date__lte=date_to)
        if search is not None:
            qs = qs.filter(note__icontains=search)
        # Newest first by transaction date, so back-dated entries land in place.
        qs = qs.order_by("-date", "-created_at", "-id")
        if cursor is not None:
            day, created_at, pk = _decode_cursor(cursor)
            qs = qs.filter(
                models.Q(date__lt=day)
                | models.Q(date=day, created_at__lt=created_at)
                | models.Q(date=day, created_at=created_at, id__lt=pk)
            )
        page = list(qs[: limit + 1])
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(page[-1])
        return [(transaction_to_domain(t), _labels(t)) for t in page], next_cursor

    def exists_for_source(self, user_id: UUID, recurring_id: UUID, date: date) -> bool:
        return TransactionORM.objects.filter(
            user_id=user_id, recurring_source_id=recurring_id, date=date
        ).exists()

    @staticmethod
    def _aggregate_qs(user_id, date_from, date_to):
        qs = TransactionORM.objects.filter(user_id=user_id, account__is_archived=False)
        if date_from is not None:
            qs = qs.filter(date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date__lte=date_to)
        return qs.order_by()

    def totals_by_type(self, user_id, *, date_from=None, date_to=None):
        rows = (
            self._aggregate_qs(user_id, date_from, date_to)
            .values("type", "account__currency")
            .annotate(total=Sum("amount"))
        )
        return _group_by_currency(rows, lambda r: TransactionType(r["type"]))

    def sum_by_category(self, user_id, *, type, date_from=None, date_to=None):
        rows = (
            self._aggregate_qs(user_id, date_from, date_to)
            .filter(type=type.value, category__isnull=False)
            .values("category_id", "account__currency")
            .annotate(total=Sum("amount"))
        )
        return _group_by_currency(rows, lambda r: r["category_id"])

    def monthly_totals(self, user_id, *, date_from=None, date_to=None):
        rows = (
            self._aggregate_qs(user_id, date_from, date_to)
            .annotate(month=TruncMonth("date"))
            .values("month", "type", "account__currency")
            .annotate(total=Sum("amount"))
        )
        return _group_by_currency(rows, lambda r: (r["month"], TransactionType(r["type"])))


class DjangoBudgetRepository(BudgetRepository):
    def add(self, budget: Budget) -> Budget:
        budget_to_orm(budget).save(force_insert=True)
        return budget

    def get_by_id(self, budget_id: UUID, user_id: UUID) -> Budget | None:
        orm = BudgetORM.objects.filter(pk=budget_id, user_id=user_id).first()
        return budget_to_domain(orm) if orm else None

    def list_for_user(self, user_id: UUID) -> list[Budget]:
        return [budget_to_domain(b) for b in BudgetORM.objects.filter(user_id=user_id)]

    def update(self, budget: Budget) -> Budget:
        BudgetORM.objects.filter(pk=budget.id, user_id=budget.user_id).update(
            category_id=budget.category_id,
            amount=budget.amount.amount,
            period=budget.period.value,
            start_date=budget.start_date,
            is_active=budget.is_active,
        )
        return budget

    def delete(self, budget_id: UUID, user_id: UUID) -> bool:
        deleted, _ = BudgetORM.objects.filter(pk=budget_id, user_id=user_id).delete()
        return deleted > 0


class DjangoExchangeRateRepository(ExchangeRateRepository):
    def add(self, rate: ExchangeRate) -> ExchangeRate:
        exchange_rate_to_orm(rate).save(force_insert=True)
        return rate

    def get_latest(self, base: CurrencyCode, target: CurrencyCode) -> ExchangeRate | None:
        orm = ExchangeRateORM.objects.filter(base=base.value, target=target.value).first()
        return exchange_rate_to_domain(orm) if orm else None
