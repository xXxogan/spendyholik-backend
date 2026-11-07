"""Domain exceptions.

Pure Python — no Django/DRF imports. Each exception carries a stable
``code`` and an ``http_status`` so the presentation layer can translate it
into the unified API error shape ``{"code", "detail", "errors"}``.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every domain-layer error."""

    code = "domain_error"
    http_status = 400
    default_detail = "Domain error."
    #: Request field the error belongs to; rendered as ``errors = {field: field_code}``.
    field: str | None = None
    #: Code reported for ``field``; defaults to :attr:`code`.
    field_code: str | None = None

    def __init__(
        self,
        detail: str | None = None,
        *,
        field: str | None = None,
        field_code: str | None = None,
    ) -> None:
        self.detail = detail or self.default_detail
        if field is not None:
            self.field = field
        if field_code is not None:
            self.field_code = field_code
        super().__init__(self.detail)

    @property
    def errors(self) -> dict[str, str]:
        return {self.field: self.field_code or self.code} if self.field else {}


class EntityNotFoundError(DomainError):
    """Base class for "resource not found" errors (maps to HTTP 404)."""

    code = "entity_not_found"
    http_status = 404
    default_detail = "Entity not found."

    def __init__(self, entity: str = "Entity", identifier: object | None = None) -> None:
        detail = f"{entity} not found"
        if identifier is not None:
            detail = f"{detail}: {identifier}"
        self.entity = entity
        self.identifier = identifier
        super().__init__(detail)


class ValidationError(DomainError):
    """A domain invariant or value-object invariant was violated (HTTP 422)."""

    code = "validation_error"
    http_status = 422
    default_detail = "Validation failed."


class BusinessRuleError(DomainError):
    """A business rule prevented the operation (HTTP 409 by default)."""

    code = "business_rule_violation"
    http_status = 409
    default_detail = "Business rule violation."


class ConflictError(BusinessRuleError):
    """A write collided with existing state (e.g. a unique constraint)."""

    code = "conflict"
    default_detail = "Conflicting state."


class CurrencyMismatchError(ValidationError):
    code = "currency_mismatch"
    default_detail = "Currency mismatch."

    def __init__(self, left: str | None = None, right: str | None = None) -> None:
        detail = self.default_detail
        if left and right:
            detail = f"Currency mismatch: cannot operate on {left} and {right}."
        super().__init__(detail)
