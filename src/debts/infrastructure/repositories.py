"""Django ORM implementations of the debts ports."""

from decimal import Decimal
from uuid import UUID

from django.db.models import Sum

from debts.application.ports import DebtPaymentRepository, DebtRepository
from debts.domain.entities import Debt, DebtPayment
from debts.infrastructure.mappers import (
    debt_to_domain,
    debt_to_orm,
    payment_to_domain,
    payment_to_orm,
)
from debts.infrastructure.orm.models import Debt as DebtORM
from debts.infrastructure.orm.models import DebtPayment as DebtPaymentORM
from shared.domain.money import DEFAULT_CURRENCY, Money


class DjangoDebtRepository(DebtRepository):
    def add(self, debt: Debt) -> Debt:
        debt_to_orm(debt).save(force_insert=True)
        return debt

    def get_by_id(self, debt_id: UUID, user_id: UUID) -> Debt | None:
        orm = DebtORM.objects.filter(pk=debt_id, user_id=user_id).first()
        return debt_to_domain(orm) if orm else None

    def list_for_user(self, user_id: UUID) -> list[Debt]:
        return [debt_to_domain(d) for d in DebtORM.objects.filter(user_id=user_id)]

    def update(self, debt: Debt) -> Debt:
        orm = DebtORM.objects.get(pk=debt.id, user_id=debt.user_id)
        orm.person_name = debt.person_name
        orm.due_date = debt.due_date
        orm.remaining = debt.remaining.amount if debt.remaining is not None else debt.amount.amount
        orm.is_closed = debt.is_closed
        orm.save()
        return debt

    def delete(self, debt_id: UUID, user_id: UUID) -> None:
        DebtORM.objects.filter(pk=debt_id, user_id=user_id).delete()


class DjangoDebtPaymentRepository(DebtPaymentRepository):
    def add(self, payment: DebtPayment) -> DebtPayment:
        payment_to_orm(payment).save(force_insert=True)
        return payment

    def list_for_debt(self, debt_id: UUID) -> list[DebtPayment]:
        return [payment_to_domain(p) for p in DebtPaymentORM.objects.filter(debt_id=debt_id)]

    def sum_for_debt(self, debt_id: UUID) -> Money:
        debt = DebtORM.objects.filter(pk=debt_id).first()
        currency = debt.currency if debt else DEFAULT_CURRENCY
        total = DebtPaymentORM.objects.filter(debt_id=debt_id).aggregate(total=Sum("amount"))["total"]
        return Money(Decimal(total or 0), currency)
