"""Django ORM models for the finances bounded context."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from finances.domain.enums import AccountType, BudgetPeriod, TransactionType


def _choices(enum_cls):
    return [(e.value, e.value) for e in enum_cls]


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts"
    )
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=_choices(AccountType))
    currency = models.CharField(max_length=3)
    initial_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    color = models.CharField(max_length=40, default="default")
    last4 = models.CharField(max_length=4, null=True, blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["user", "is_archived"]),
        ]

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=_choices(TransactionType))
    icon = models.CharField(max_length=40, default="tag")
    color = models.CharField(max_length=40, default="default")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["user", "type"]),
        ]

    def __str__(self) -> str:
        return self.name


class Transaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="transactions")
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    type = models.CharField(max_length=20, choices=_choices(TransactionType))
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField(db_index=True)
    time = models.TimeField(null=True, blank=True)
    note = models.TextField(max_length=2000, blank=True, default="")
    title = models.CharField(max_length=120, blank=True, default="")
    receipt_id = models.UUIDField(null=True, blank=True)
    transfer_to_account = models.ForeignKey(
        Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="incoming_transfers"
    )
    recurring_source_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-date", "-created_at")
        indexes = [
            # Serves the feed ordering/cursor and date-range aggregates.
            models.Index(fields=["user", "-date", "-created_at", "-id"], name="tx_user_feed_idx"),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["user", "recurring_source_id", "date"]),
        ]
        constraints = [
            # Makes recurring generation idempotent even under concurrent runs.
            models.UniqueConstraint(
                fields=["recurring_source_id", "date"],
                condition=models.Q(recurring_source_id__isnull=False),
                name="uniq_tx_recurring_source_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.amount}"


class Budget(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets"
    )
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="budgets")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="RUB")
    period = models.CharField(
        max_length=20, choices=_choices(BudgetPeriod), default=BudgetPeriod.MONTHLY.value
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-is_active", "category__name")
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.category_id} {self.amount}"


class ExchangeRate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base = models.CharField(max_length=3)
    target = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    date = models.DateField()

    class Meta:
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(
                fields=["base", "target", "date"], name="uniq_rate_base_target_date"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.base}/{self.target}={self.rate}"
