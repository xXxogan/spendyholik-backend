"""Domain exceptions for the goals bounded context."""

from __future__ import annotations

from shared.exceptions import BusinessRuleError, EntityNotFoundError


class GoalTargetExceededError(BusinessRuleError):
    code = "exceeds_target"
    default_detail = "The contribution exceeds what is left to the goal's target."
    field = "amount_minor"


class GoalNotFoundError(EntityNotFoundError):
    code = "goal_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Goal", identifier)
