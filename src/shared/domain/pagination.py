"""Domain-level pagination value objects (framework-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from shared.exceptions import ValidationError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page:
    """A 1-based page request."""

    number: int
    size: int

    def __post_init__(self) -> None:
        if self.number < 1:
            msg = "Page number must be >= 1"
            raise ValidationError(msg)
        if self.size < 1:
            msg = "Page size must be >= 1"
            raise ValidationError(msg)

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size


@dataclass(frozen=True, slots=True)
class Cursor:
    """An opaque cursor used for cursor-based pagination."""

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """A page of domain items with optional pagination metadata."""

    items: list[T]
    total: int | None = None
    page: Page | None = None
    next_cursor: Cursor | None = None
    previous_cursor: Cursor | None = None
