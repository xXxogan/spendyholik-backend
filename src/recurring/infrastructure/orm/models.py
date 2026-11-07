"""Django ORM models for the recurring bounded context."""

import uuid

from django.conf import settings
from django.db import models

from finances.domain.enums import TransactionType
from recurring.domain.enums import RecurringFrequency


def _choices(enum_cls):
    return [(e.value, e.value) for e in enum_cls]


class RecurringTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recurring_transactions"
    )
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    type = models.CharField(max_length=20, choices=_choices(TransactionType))
    account = models.ForeignKey(
        "finances.Account", on_delete=models.CASCADE, related_name="recurring_transactions"
    )
    category = models.ForeignKey(
        "finances.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurring_transactions",
    )
    frequency = models.CharField(max_length=20, choices=_choices(RecurringFrequency))
    next_run = models.DateField(db_index=True)
    is_active = models.BooleanField(default=True)
    # Schedule origin (see the domain entity); NULL means "same as next_run".
    anchor = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("next_run",)
