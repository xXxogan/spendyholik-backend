"""Production settings — hardened, secrets from environment only."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# TLS / security hardening
# ---------------------------------------------------------------------------
# Set SECURE_SSL_REDIRECT/SECURE_COOKIES to false only while serving plain HTTP
# (e.g. before a domain and certificate exist).
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# Probes and metrics are scraped over plain HTTP inside the cluster.
SECURE_REDIRECT_EXEMPT = [r"^health/$", r"^ready/$", r"^metrics$"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Static / media — static files are collected at image build time and served
# by WhiteNoise; media lives on the PVC mounted at MEDIA_ROOT.
# ---------------------------------------------------------------------------
MIDDLEWARE = [  # noqa: F405
    *MIDDLEWARE[:2],  # noqa: F405 — Prometheus + SecurityMiddleware first
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[2:],  # noqa: F405
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
