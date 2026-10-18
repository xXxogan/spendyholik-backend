"""ORM ↔ domain mappers for the finances bounded context."""

from __future__ import annotations

from decimal import Decimal

from finances.domain.entities import Account, Budget, Category, ExchangeRate, Transaction
from finances.domain.enums import AccountType, BudgetPeriod, TransactionType
from finances.domain.value_objects import CategoryColor
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


def account_to_domain(orm: AccountORM) -> Account:
    return Account(
        id=orm.id,
        user_id=orm.user_id,
        name=orm.name,
        type=AccountType(orm.type),
        currency=CurrencyCode(orm.currency),
        initial_balance=Money(Decimal(orm.initial_balance), orm.currency),
        color=CategoryColor(orm.color),
        last4=orm.last4,
        credit_limit=Money(Decimal(orm.credit_limit), orm.currency)
        if orm.credit_limit is not None
        else None,
        interest_rate=Decimal(orm.interest_rate),
        is_archived=orm.is_archived,
    )


def account_to_orm(account: Account) -> AccountORM:
    return AccountORM(
        id=account.id,
        user_id=account.user_id,
        name=account.name,
        type=account.type.value,
        currency=account.currency.value,
        initial_balance=account.initial_balance.amount,
        color=account.color.value,
        last4=account.last4,
        credit_limit=account.credit_limit.amount if account.credit_limit is not None else None,
        interest_rate=account.interest_rate,
        is_archived=account.is_archived,
    )


def category_to_domain(orm: CategoryORM) -> Category:
    return Category(
        id=orm.id,
        user_id=orm.user_id,
        name=orm.name,
        type=TransactionType(orm.type),
        icon=orm.icon,
        color=CategoryColor(orm.color),
        parent_id=orm.parent_id,
        is_system=orm.is_system,
    )


def category_to_orm(category: Category) -> CategoryORM:
    return CategoryORM(
        id=category.id,
        user_id=category.user_id,
        name=category.name,
        type=category.type.value,
        icon=category.icon,
        color=category.color.value,
        parent_id=category.parent_id,
        is_system=category.is_system,
    )


def transaction_to_domain(orm: TransactionORM) -> Transaction:
    return Transaction(
        id=orm.id,
        user_id=orm.user_id,
        account_id=orm.account_id,
        category_id=orm.category_id,
        type=TransactionType(orm.type),
        amount=Money(Decimal(orm.amount), orm.account.currency),
        date=orm.date,
        time=orm.time,
        note=orm.note,
        receipt_id=orm.receipt_id,
        transfer_to_account_id=orm.transfer_to_account_id,
        recurring_source_id=orm.recurring_source_id,
    )


def transaction_to_orm(transaction: Transaction) -> TransactionORM:
    return TransactionORM(
        id=transaction.id,
        user_id=transaction.user_id,
        account_id=transaction.account_id,
        category_id=transaction.category_id,
        type=transaction.type.value,
        amount=transaction.amount.amount,
        date=transaction.date,
        time=transaction.time,
        note=transaction.note,
        receipt_id=transaction.receipt_id,
        transfer_to_account_id=transaction.transfer_to_account_id,
        recurring_source_id=transaction.recurring_source_id,
    )


def budget_to_domain(orm: BudgetORM) -> Budget:
    return Budget(
        id=orm.id,
        user_id=orm.user_id,
        category_id=orm.category_id,
        amount=Money(Decimal(orm.amount), "RUB"),
        period=BudgetPeriod(orm.period),
        start_date=orm.start_date,
        is_active=orm.is_active,
    )


def budget_to_orm(budget: Budget) -> BudgetORM:
    return BudgetORM(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        amount=budget.amount.amount,
        period=budget.period.value,
        start_date=budget.start_date,
        is_active=budget.is_active,
    )


def exchange_rate_to_domain(orm: ExchangeRateORM) -> ExchangeRate:
    return ExchangeRate(
        id=orm.id,
        base=CurrencyCode(orm.base),
        target=CurrencyCode(orm.target),
        rate=Decimal(orm.rate),
        date=orm.date,
    )


def exchange_rate_to_orm(rate: ExchangeRate) -> ExchangeRateORM:
    return ExchangeRateORM(
        id=rate.id, base=rate.base.value, target=rate.target.value, rate=rate.rate, date=rate.date
    )
