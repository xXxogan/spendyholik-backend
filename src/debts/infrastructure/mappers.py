"""ORM ↔ domain mappers for the debts bounded context."""

from decimal import Decimal

from debts.domain.entities import Debt, DebtPayment
from debts.domain.enums import DebtDirection
from debts.infrastructure.orm.models import Debt as DebtORM
from debts.infrastructure.orm.models import DebtPayment as DebtPaymentORM
from shared.domain.money import Money


def debt_to_domain(orm: DebtORM) -> Debt:
    return Debt(
        id=orm.id,
        user_id=orm.user_id,
        person_name=orm.person_name,
        direction=DebtDirection(orm.direction),
        amount=Money(Decimal(orm.amount), orm.currency),
        remaining=Money(Decimal(orm.remaining), orm.currency),
        due_date=orm.due_date,
        is_closed=orm.is_closed,
        note=orm.note,
        created_at=orm.created_at,
    )


def debt_to_orm(d: Debt) -> DebtORM:
    return DebtORM(
        id=d.id,
        user_id=d.user_id,
        person_name=d.person_name,
        direction=d.direction.value,
        amount=d.amount.amount,
        remaining=d.remaining.amount if d.remaining is not None else d.amount.amount,
        currency=d.amount.currency,
        due_date=d.due_date,
        is_closed=d.is_closed,
        note=d.note,
        **({"created_at": d.created_at} if d.created_at else {}),
    )


def payment_to_domain(orm: DebtPaymentORM) -> DebtPayment:
    return DebtPayment(
        id=orm.id,
        debt_id=orm.debt_id,
        account_id=orm.account_id,
        amount=Money(Decimal(orm.amount), orm.currency),
        date=orm.date,
    )


def payment_to_orm(p: DebtPayment) -> DebtPaymentORM:
    return DebtPaymentORM(
        id=p.id,
        debt_id=p.debt_id,
        account_id=p.account_id,
        amount=p.amount.amount,
        currency=p.amount.currency,
        date=p.date,
    )
