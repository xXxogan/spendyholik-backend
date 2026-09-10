"""Django ORM implementations of the recurring ports."""

from datetime import date
from uuid import UUID

from recurring.application.ports import RecurringTransactionRepository
from recurring.domain.entities import RecurringTransaction
from recurring.infrastructure.mappers import recurring_to_domain, recurring_to_orm
from recurring.infrastructure.orm.models import RecurringTransaction as RecurringORM


class DjangoRecurringTransactionRepository(RecurringTransactionRepository):
    def add(self, recurring: RecurringTransaction) -> RecurringTransaction:
        recurring_to_orm(recurring).save(force_insert=True)
        return recurring

    def get_by_id(self, recurring_id: UUID, user_id: UUID) -> RecurringTransaction | None:
        orm = RecurringORM.objects.filter(pk=recurring_id, user_id=user_id).first()
        return recurring_to_domain(orm) if orm else None

    def list_for_user(self, user_id: UUID) -> list[RecurringTransaction]:
        return [recurring_to_domain(r) for r in RecurringORM.objects.filter(user_id=user_id)]

    def update(self, recurring: RecurringTransaction) -> RecurringTransaction:
        orm = RecurringORM.objects.get(pk=recurring.id, user_id=recurring.user_id)
        orm.name = recurring.name
        orm.amount = recurring.amount.amount
        orm.account_id = recurring.account_id
        orm.category_id = recurring.category_id
        orm.frequency = recurring.frequency.value
        orm.next_run = recurring.next_run
        orm.is_active = recurring.is_active
        orm.save()
        return recurring

    def delete(self, recurring_id: UUID, user_id: UUID) -> None:
        RecurringORM.objects.filter(pk=recurring_id, user_id=user_id).delete()

    def list_due(self, on: date) -> list[RecurringTransaction]:
        return [
            recurring_to_domain(r)
            for r in RecurringORM.objects.filter(next_run__lte=on, is_active=True)
        ]
