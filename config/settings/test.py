"""Test settings — fast hashers, eager Celery, isolated database."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Speed up password hashing in tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Run Celery tasks synchronously in tests unless explicitly tested.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# A dedicated test database URL may be provided; otherwise reuse the default.
DATABASES = {
    "default": env.db("TEST_DATABASE_URL", default=env("DATABASE_URL", default="sqlite://:memory:"))
}

RATELIMIT_ENABLE = False

# Disable the live external exchange-rate provider during tests.
EXCHANGE_RATE_PROVIDER = "stub"
