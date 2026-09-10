"""Development settings — never used in production."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Log more verbosely during development.
LOGGING["root"]["level"] = env("LOG_LEVEL", default="DEBUG")  # noqa: F405
