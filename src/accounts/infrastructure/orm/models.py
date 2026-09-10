"""Django ORM models for the accounts bounded context.

The domain layer stays free of Django imports; these ORM models are mapped
to/from domain entities by ``accounts.infrastructure.mappers``.
"""

import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields) -> "User":
        if not email:
            msg = "Users must have an email address."
            raise ValueError(msg)
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            msg = "Superuser must have is_staff=True."
            raise ValueError(msg)
        if extra_fields.get("is_superuser") is not True:
            msg = "Superuser must have is_superuser=True."
            raise ValueError(msg)
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", unique=True, db_index=True)
    first_name = models.CharField("first name", max_length=150, blank=True)
    is_staff = models.BooleanField("staff status", default=False)
    is_active = models.BooleanField("active", default=True)
    date_joined = models.DateTimeField("date joined", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        return self.first_name or self.email.split("@", 1)[0]


class Profile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", primary_key=True
    )
    base_currency = models.CharField(max_length=3, default="RUB")
    theme = models.CharField(max_length=10, default="auto")
    onboarded = models.BooleanField(default=False)
    notify_budget = models.BooleanField(default=True)
    notify_goal = models.BooleanField(default=True)
    notify_recurring = models.BooleanField(default=True)
    notify_weekly_report = models.BooleanField(default=True)

    class Meta:
        verbose_name = "profile"
        verbose_name_plural = "profiles"

    def __str__(self) -> str:
        return f"Profile({self.user_id})"
