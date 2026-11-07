"""Domain exceptions for the notifications bounded context."""

from __future__ import annotations

from shared.exceptions import EntityNotFoundError


class NotificationNotFoundError(EntityNotFoundError):
    code = "notification_not_found"

    def __init__(self, identifier: object | None = None) -> None:
        super().__init__("Notification", identifier)
