"""Domain entities for the notifications bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from notifications.domain.enums import NotificationType


@dataclass(frozen=True, slots=True)
class Notification:
    """A feed entry.

    ``subject`` names what it is about (budget category, income source,
    recurring template, goal); ``amount_minor`` and ``percent`` carry the
    numbers. ``title``/``body`` are an optional ready-made text (e.g. for push).
    """

    user_id: UUID
    type: NotificationType
    subject: str = ""
    amount_minor: int | None = None
    #: Currency of ``amount_minor``.
    currency: str = ""
    percent: int | None = None
    title: str = ""
    body: str = ""
    is_read: bool = False
    created_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
