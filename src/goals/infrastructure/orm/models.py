"""Django ORM models for the goals bounded context."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Goal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    initial_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3)
    account = models.ForeignKey(
        "finances.Account", on_delete=models.SET_NULL, null=True, related_name="goals"
    )
    deadline = models.DateField(null=True, blank=True)
    icon = models.CharField(max_length=40, default="flag")
    color = models.CharField(max_length=40, default="goal")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class GoalContribution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    account = models.ForeignKey(
        "finances.Account", on_delete=models.SET_NULL, null=True, related_name="goal_contributions"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    date = models.DateField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("-date",)
