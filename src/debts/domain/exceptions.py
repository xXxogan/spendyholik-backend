"""Domain exceptions for the debts bounded context."""

from __future__ import annotations

from shared.exceptions import BusinessRuleError, EntityNotFoundError, ValidationError


class DebtAlreadyClosedError(BusinessRuleError):
    code = "debt_already_closed"
    default_detail = "The debt is already closed."


class ExcessiveRepaymentError(ValidationError):
    code = "excessive_repayment"
    default_detail = "The repayment exceeds the remaining debt."


class DebtNotFoundError(EntityNotFoundError):
    code = "debt_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Debt", identifier)
