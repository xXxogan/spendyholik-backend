"""Django ORM implementations of the finances ports."""

from __future__ import annotations

import base64
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import models
from django.db.models import Sum
from django.db.models.functions import TruncMonth

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
    Budget as BudgetORM,
    Category as CategoryORM,
    ExchangeRate as ExchangeRateORM,
    Transaction as TransactionORM,
)
from shared.domain.currency_code import CurrencyCode
from shared.domain.money import DEFAULT_CURRENCY, Money


def _encode_cursor(created_at: datetime, pk: UUID) -> str:
    raw = f"{created_at.isoformat()}::{pk}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, _, pk = raw.partition("::")
    return datetime.fromisoformat(ts), UUID(pk)


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
        orm = AccountORM.objects.get(pk=account.id, user_id=account.user_id)
        orm.name = account.name
        orm.type = account.type.value
        orm.color = account.color.value
        orm.last4 = account.last4
        orm.credit_limit = account.credit_limit.amount if account.credit_limit is not None else None
        orm.interest_rate = account.interest_rate
        orm.is_archived = account.is_archived
        orm.save()
        return account

    def delete(self, account_id: UUID, user_id: UUID) -> None:
        AccountORM.objects.filter(pk=account_id, user_id=user_id).delete()


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
        orm = CategoryORM.objects.get(pk=category.id, user_id=category.user_id)
        orm.name = category.name
        orm.icon = category.icon
        orm.color = category.color.value
        orm.parent_id = category.parent_id
        orm.save()
        return category

    def delete(self, category_id: UUID, user_id: UUID) -> None:
        CategoryORM.objects.filter(pk=category_id, user_id=user_id).delete()

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
        transaction_to_orm(transaction).save(force_insert=True)
        return transaction

    def get_by_id(self, transaction_id: UUID, user_id: UUID) -> Transaction | None:
        orm = TransactionORM.objects.filter(pk=transaction_id, user_id=user_id).select_related("account").first()
        return transaction_to_domain(orm) if orm else None

    def update(self, transaction: Transaction) -> Transaction:
        orm = TransactionORM.objects.get(pk=transaction.id, user_id=transaction.user_id)
        fresh = transaction_to_orm(transaction)
        for field in ("account_id", "category_id", "type", "amount", "date", "time", "note",
                      "receipt_id", "transfer_to_account_id", "recurring_source_id"):
            setattr(orm, field, getattr(fresh, field))
        orm.save()
        return transaction

    def delete(self, transaction_id: UUID, user_id: UUID) -> None:
        TransactionORM.objects.filter(pk=transaction_id, user_id=user_id).delete()

    def list_for_user(self, user_id, *, account_id=None, category_id=None, type=None,
                      date_from=None, date_to=None, search=None, cursor=None, limit=20):
        qs = TransactionORM.objects.filter(user_id=user_id).select_related("account")
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
        qs = qs.order_by("-created_at", "-id")
        if cursor is not None:
            created_at, pk = _decode_cursor(cursor)
            qs = qs.filter(models.Q(created_at__lt=created_at) | models.Q(created_at=created_at, id__lt=pk))
        page = list(qs[: limit + 1])
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = _encode_cursor(page[-1].created_at, page[-1].id)
        return [transaction_to_domain(t) for t in page], next_cursor

    def exists_for_source(self, user_id: UUID, recurring_id: UUID, date: date) -> bool:
        return TransactionORM.objects.filter(
            user_id=user_id, recurring_source_id=recurring_id, date=date
        ).exists()

    def total_amount(self, user_id, *, type=None, account_id=None, category_id=None,
                     date_from=None, date_to=None):
        qs = TransactionORM.objects.filter(user_id=user_id)
        if type is not None:
            qs = qs.filter(type=type.value)
        if account_id is not None:
            qs = qs.filter(account_id=account_id)
        if category_id is not None:
            qs = qs.filter(category_id=category_id)
        if date_from is not None:
            qs = qs.filter(date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date__lte=date_to)
        total = qs.aggregate(total=Sum("amount"))["total"]
        if total is None:
            return None
        return Money(Decimal(total), DEFAULT_CURRENCY)

    def sum_by_category(self, user_id, *, type, date_from=None, date_to=None):
        qs = TransactionORM.objects.filter(user_id=user_id, type=type.value, category__isnull=False)
        if date_from is not None:
            qs = qs.filter(date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date__lte=date_to)
        rows = qs.values("category_id").annotate(total=Sum("amount"))
        return {r["category_id"]: Money(Decimal(r["total"]), DEFAULT_CURRENCY) for r in rows}

    def monthly_totals(self, user_id, *, type, date_from=None, date_to=None):
        qs = TransactionORM.objects.filter(user_id=user_id, type=type.value)
        if date_from is not None:
            qs = qs.filter(date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date__lte=date_to)
        rows = qs.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount"))
        return [(r["month"], Money(Decimal(r["total"]), DEFAULT_CURRENCY)) for r in rows]


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
        orm = BudgetORM.objects.get(pk=budget.id, user_id=budget.user_id)
        orm.category_id = budget.category_id
        orm.amount = budget.amount.amount
        orm.period = budget.period.value
        orm.start_date = budget.start_date
        orm.is_active = budget.is_active
        orm.save()
        return budget

    def delete(self, budget_id: UUID, user_id: UUID) -> None:
        BudgetORM.objects.filter(pk=budget_id, user_id=user_id).delete()


class DjangoExchangeRateRepository(ExchangeRateRepository):
    def add(self, rate: ExchangeRate) -> ExchangeRate:
        exchange_rate_to_orm(rate).save(force_insert=True)
        return rate

    def get_latest(self, base: CurrencyCode, target: CurrencyCode) -> ExchangeRate | None:
        orm = ExchangeRateORM.objects.filter(base=base.value, target=target.value).first()
        return exchange_rate_to_domain(orm) if orm else None
