"""Domain entities for the notifications bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from notifications.domain.enums import NotificationType


@dataclass(frozen=True, slots=True)
class Notification:
    user_id: UUID
    type: NotificationType
    title: str
    body: str = ""
    is_read: bool = False
    id: UUID = field(default_factory=uuid4)
