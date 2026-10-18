"""Unified DRF exception handler.

Translates domain exceptions and DRF errors into a single API error shape:
``{"code": "...", "detail": "...", "errors": {...}}``.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

from shared.exceptions import DomainError


def _error_response(
    code: str, detail: str, errors: dict | None = None, status: int = 400
) -> Response:
    return Response(
        {"code": code, "detail": detail, "errors": errors or {}},
        status=status,
    )


def exception_handler(exc: Exception, context: dict) -> Response | None:
    if isinstance(exc, DomainError):
        set_rollback()
        return _error_response(exc.code, exc.detail, status=exc.http_status)

    if isinstance(exc, Http404):
        set_rollback()
        return _error_response("not_found", "Not found.", status=404)

    # Validation / parse errors are "unprocessable" (422), not generic 400.
    if isinstance(exc, (drf_exceptions.ValidationError, drf_exceptions.ParseError)):
        set_rollback()
        detail = getattr(exc, "detail", "Validation failed.")
        errors = {}
        if isinstance(detail, dict):
            errors = {k: v for k, v in detail.items() if k != "detail"}
        return _error_response("validation_error", "Validation failed.", errors, status=422)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled → 500

    # Re-wrap DRF's own responses (401/403/404/405/429, ...) into the unified shape.
    set_rollback()
    code = getattr(exc, "default_code", "error")
    data = response.data
    if isinstance(data, dict):
        detail = data.get("detail", "Request failed.")
        errors = {k: v for k, v in data.items() if k != "detail"}
        return _error_response(code, str(detail), errors, status=response.status_code)
    return _error_response(code, str(data), status=response.status_code)
