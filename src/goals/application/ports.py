"""Ports for the goals bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from goals.domain.entities import Goal, GoalContribution
from shared.domain.money import Money


class GoalRepository(ABC):
    @abstractmethod
    def add(self, goal: Goal) -> Goal: ...

    @abstractmethod
    def get_by_id(self, goal_id: UUID, user_id: UUID) -> Goal | None: ...

    @abstractmethod
    def list_for_user(self, user_id: UUID) -> list[Goal]: ...

    @abstractmethod
    def update(self, goal: Goal) -> Goal: ...

    @abstractmethod
    def delete(self, goal_id: UUID, user_id: UUID) -> None: ...


class GoalContributionRepository(ABC):
    @abstractmethod
    def add(self, contribution: GoalContribution) -> GoalContribution: ...

    @abstractmethod
    def list_for_goal(self, goal_id: UUID) -> list[GoalContribution]: ...

    @abstractmethod
    def sum_for_goal(self, goal_id: UUID) -> Money: ...
