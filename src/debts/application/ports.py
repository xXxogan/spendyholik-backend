"""Ports for the debts bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from debts.domain.entities import Debt, DebtPayment
from shared.domain.money import Money


class DebtRepository(ABC):
    @abstractmethod
    def add(self, debt: Debt) -> Debt: ...

    @abstractmethod
    def get_by_id(self, debt_id: UUID, user_id: UUID) -> Debt | None: ...

    @abstractmethod
    def list_for_user(self, user_id: UUID) -> list[Debt]: ...

    @abstractmethod
    def update(self, debt: Debt) -> Debt: ...

    @abstractmethod
    def delete(self, debt_id: UUID, user_id: UUID) -> None: ...


class DebtPaymentRepository(ABC):
    @abstractmethod
    def add(self, payment: DebtPayment) -> DebtPayment: ...

    @abstractmethod
    def list_for_debt(self, debt_id: UUID) -> list[DebtPayment]: ...

    @abstractmethod
    def sum_for_debt(self, debt_id: UUID) -> Money: ...
