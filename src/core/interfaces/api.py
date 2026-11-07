"""Shared helpers for the DRF presentation layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

#: pydantic error type → stable field-error code the client translates.
_ERROR_CODES = {
    "missing": "required",
    "string_too_long": "too_long",
    "too_long": "too_long",
    "too_short": "too_short",
    "greater_than": "too_small",
    "greater_than_equal": "too_small",
    "less_than": "too_large",
    "less_than_equal": "too_large",
    "enum": "invalid_choice",
    "literal_error": "invalid_choice",
}


def field_error_code(err: dict) -> str:
    """Map one pydantic error to a code: ``required``, ``too_long``, ``invalid``…"""
    kind = err["type"]
    if kind == "string_too_short":
        # An empty value for a required text field is "required", not "too short".
        return "required" if err.get("ctx", {}).get("min_length") == 1 else "too_short"
    return _ERROR_CODES.get(kind, "invalid")


def validation_errors(exc: PydanticValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for err in exc.errors():
        field = str(err["loc"][0]) if err["loc"] else "non_field"
        errors.setdefault(field, field_error_code(err))
    return errors


class BaseAPIView(APIView):
    """Thin adapter over use cases — no business logic here."""

    def parse(self, model: type[BaseModel], data: Any) -> BaseModel:
        try:
            return model.model_validate(data)
        except PydanticValidationError as exc:
            raise DRFValidationError(validation_errors(exc)) from exc


def query_int(request, name: str, default: int) -> int:
    """An integer query parameter; a malformed value is a 422 ``{name: "invalid"}``."""
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise DRFValidationError({name: "invalid"}) from exc


def ok(data: Any, status: int = 200) -> Response:
    return Response(data, status=status)


def created(data: Any) -> Response:
    return Response(data, status=201)


def no_content() -> Response:
    return Response(status=204)
