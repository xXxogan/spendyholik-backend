"""DRF permissions shared by the API views."""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated

from accounts.domain.exceptions import EmailNotVerifiedError


class IsVerified(IsAuthenticated):
    """Authenticated and with a confirmed email; otherwise 403 ``email_not_verified``.

    Auth, profile and email-confirmation endpoints use plain ``IsAuthenticated``,
    so an unconfirmed user can still read the profile and enter the code.
    """

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if not getattr(request.user, "email_verified", True):
            raise EmailNotVerifiedError
        return True
