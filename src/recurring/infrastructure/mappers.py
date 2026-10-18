"""ORM ↔ domain mappers for the recurring bounded context."""

from decimal import Decimal

from finances.domain.enums import TransactionType
from recurring.domain.entities import RecurringTransaction
from recurring.domain.enums import RecurringFrequency
from recurring.infrastructure.orm.models import RecurringTransaction as RecurringORM
from shared.domain.money import Money


def recurring_to_domain(orm: RecurringORM) -> RecurringTransaction:
    return RecurringTransaction(
        id=orm.id,
        user_id=orm.user_id,
        name=orm.name,
        amount=Money(Decimal(orm.amount), orm.currency),
        type=TransactionType(orm.type),
        account_id=orm.account_id,
        category_id=orm.category_id,
        frequency=RecurringFrequency(orm.frequency),
        next_run=orm.next_run,
        is_active=orm.is_active,
    )


def recurring_to_orm(r: RecurringTransaction) -> RecurringORM:
    return RecurringORM(
        id=r.id,
        user_id=r.user_id,
        name=r.name,
        amount=r.amount.amount,
        currency=r.amount.currency,
        type=r.type.value,
        account_id=r.account_id,
        category_id=r.category_id,
        frequency=r.frequency.value,
        next_run=r.next_run,
        is_active=r.is_active,
    )
