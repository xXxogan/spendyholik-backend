"""Django ORM models for the debts bounded context."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from debts.domain.enums import DebtDirection


def _choices(enum_cls):
    return [(e.value, e.value) for e in enum_cls]


class Debt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="debts"
    )
    person_name = models.CharField(max_length=120)
    direction = models.CharField(max_length=20, choices=_choices(DebtDirection))
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    remaining = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    due_date = models.DateField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)
    note = models.TextField(max_length=2000, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    account = models.ForeignKey(
        "finances.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opened_debts",
    )
    opened_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-is_closed", "due_date")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(remaining__gte=0) & models.Q(remaining__lte=models.F("amount")),
                name="debt_remaining_within_amount",
            ),
        ]


class DebtPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="payments")
    account = models.ForeignKey(
        "finances.Account", on_delete=models.SET_NULL, null=True, related_name="debt_payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    date = models.DateField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("-date",)
