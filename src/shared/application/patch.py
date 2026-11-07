"""PATCH semantics for frozen domain entities.

Only fields the client actually sent (``model_fields_set``) are applied, so an
omitted field keeps its value while an explicit ``null`` clears a nullable one.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import replace
from typing import Any

from pydantic import BaseModel

from shared.exceptions import ValidationError

#: Input field → (entity field, converter applied to non-null values).
type FieldMap = Mapping[str, tuple[str, Callable[[Any], Any]]]


def apply_patch[E](
    entity: E,
    data: BaseModel,
    *,
    fields: FieldMap | None = None,
    nullable: Collection[str] = (),
    only: Collection[str] | None = None,
) -> E:
    """Return ``entity`` with the sent fields of ``data`` applied.

    Input fields are copied to the entity field of the same name unless
    ``fields`` maps them elsewhere (optionally converting the value). Sending
    ``null`` for a field not listed in ``nullable`` is a validation error.
    ``only`` restricts the patch to those input fields (one input feeding
    several entities).
    """
    fields = fields or {}
    changes: dict[str, Any] = {}
    sent = data.model_fields_set if only is None else data.model_fields_set & set(only)
    for name in sent:
        value = getattr(data, name)
        target, convert = fields.get(name, (name, _identity))
        if value is None:
            if name not in nullable:
                msg = f"{name} cannot be null."
                raise ValidationError(msg, field=name, field_code="required")
            changes[target] = None
        else:
            changes[target] = convert(value)
    return replace(entity, **changes) if changes else entity


def _identity(value: Any) -> Any:
    return value
