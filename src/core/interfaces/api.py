"""Shared helpers for the DRF presentation layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError as PydanticValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView


class BaseAPIView(APIView):
    """Thin adapter over use cases — no business logic here."""

    def parse(self, model: type[BaseModel], data: Any) -> BaseModel:
        try:
            return model.model_validate(data)
        except PydanticValidationError as exc:
            errors = {err["loc"][0] if err["loc"] else "non_field": err["msg"] for err in exc.errors()}
            raise DRFValidationError({"code": "validation_error", "detail": "Validation failed.", "errors": errors}) from exc


def ok(data: Any, status: int = 200) -> Response:
    return Response(data, status=status)


def created(data: Any) -> Response:
    return Response(data, status=201)
