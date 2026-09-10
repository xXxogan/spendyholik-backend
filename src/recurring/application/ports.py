"""Ports for the recurring bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from recurring.domain.entities import RecurringTransaction


class RecurringTransactionRepository(ABC):
    @abstractmethod
    def add(self, recurring: RecurringTransaction) -> RecurringTransaction: ...

    @abstractmethod
    def get_by_id(self, recurring_id: UUID, user_id: UUID) -> RecurringTransaction | None: ...

    @abstractmethod
    def list_for_user(self, user_id: UUID) -> list[RecurringTransaction]: ...

    @abstractmethod
    def update(self, recurring: RecurringTransaction) -> RecurringTransaction: ...

    @abstractmethod
    def delete(self, recurring_id: UUID, user_id: UUID) -> None: ...

    @abstractmethod
    def list_due(self, on: date) -> list[RecurringTransaction]: ...
