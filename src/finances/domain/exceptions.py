"""Domain exceptions for the finances bounded context."""

from __future__ import annotations

from shared.exceptions import BusinessRuleError, EntityNotFoundError, ValidationError


class AccountArchivedError(BusinessRuleError):
    code = "account_archived"
    default_detail = "The account is archived and cannot be used."


class CategoryInUseError(BusinessRuleError):
    code = "category_in_use"
    default_detail = "The category is in use and cannot be deleted."


class CategoryCycleError(ValidationError):
    code = "category_cycle"
    default_detail = "The category hierarchy would create a cycle."


class BudgetAlreadyExistsError(BusinessRuleError):
    code = "budget_already_exists"
    default_detail = "The category already has a budget."
    field = "category_id"


class InsufficientFundsError(BusinessRuleError):
    code = "insufficient_funds"
    default_detail = "The account balance is too low for this amount."
    field = "amount_minor"


class TransferCurrencyMismatchError(ValidationError):
    code = "currency_mismatch"
    default_detail = "A transfer needs two accounts in the same currency."
    field = "transfer_to_account_id"


class BudgetNotFoundError(EntityNotFoundError):
    code = "budget_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Budget", identifier)


class InsufficientExchangeRateError(BusinessRuleError):
    code = "insufficient_exchange_rate"
    default_detail = "No exchange rate is available for the requested currency pair."


class AccountNotFoundError(EntityNotFoundError):
    code = "account_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Account", identifier)


class CategoryNotFoundError(EntityNotFoundError):
    code = "category_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Category", identifier)


class TransactionNotFoundError(EntityNotFoundError):
    code = "transaction_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Transaction", identifier)
