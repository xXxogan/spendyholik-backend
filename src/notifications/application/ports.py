"""Ports for the notifications bounded context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from notifications.domain.entities import Notification


class NotificationRepository(ABC):
    @abstractmethod
    def add(self, notification: Notification) -> Notification: ...

    @abstractmethod
    def add_once(self, notification: Notification, key: str) -> bool:
        """Add unless the user already has a notification with ``key``; True if added."""

    @abstractmethod
    def list_for_user(self, user_id: UUID) -> list[Notification]: ...

    @abstractmethod
    def unread_count(self, user_id: UUID) -> int: ...

    @abstractmethod
    def mark_read(self, user_id: UUID, notification_id: UUID) -> bool:
        """Mark one notification read; ``False`` if the user has no such notification."""

    @abstractmethod
    def mark_all_read(self, user_id: UUID) -> None: ...
