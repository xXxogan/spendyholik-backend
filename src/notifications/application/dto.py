"""DTOs for the notifications application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from notifications.domain.enums import NotificationType


@dataclass(frozen=True, slots=True)
class NotificationDTO:
    id: UUID
    type: NotificationType
    subject: str
    amount_minor: int | None
    currency: str
    percent: int | None
    title: str
    body: str
    is_read: bool
    created_at: datetime | None
