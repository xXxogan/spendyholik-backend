"""Domain exceptions for the goals bounded context."""

from __future__ import annotations

from shared.exceptions import EntityNotFoundError


class GoalNotFoundError(EntityNotFoundError):
    code = "goal_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Goal", identifier)
