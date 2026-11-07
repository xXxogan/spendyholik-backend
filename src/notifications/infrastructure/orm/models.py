"""Django ORM models for the notifications bounded context."""

import uuid

from django.conf import settings
from django.db import models

from notifications.domain.enums import NotificationType


def _choices(enum_cls):
    return [(e.value, e.value) for e in enum_cls]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=30, choices=_choices(NotificationType))
    subject = models.CharField(max_length=200, blank=True, default="")
    amount_minor = models.BigIntegerField(null=True, blank=True)
    percent = models.PositiveSmallIntegerField(null=True, blank=True)
    title = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "is_read"]),
        ]
