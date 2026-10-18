"""Health / readiness views (k8s probes)."""

import logging

from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from core.interfaces.api import BaseAPIView, ok

logger = logging.getLogger(__name__)


class _ProbeView(BaseAPIView):
    # Probes must not depend on (or fail because of) an Authorization header.
    authentication_classes = []
    permission_classes = [AllowAny]


class HealthView(_ProbeView):
    def get(self, request: Request):
        return ok({"status": "ok"})


class ReadyView(_ProbeView):
    def get(self, request: Request):
        checks = {"database": self._database(), "cache": self._cache()}
        ready = all(checks.values())
        return Response(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status=200 if ready else 503,
        )

    @staticmethod
    def _database() -> bool:
        try:
            connection.ensure_connection()
        except Exception:
            logger.exception("Readiness: database unavailable")
            return False
        return True

    @staticmethod
    def _cache() -> bool:
        try:
            cache.set("ready-probe", "1", timeout=5)
            return cache.get("ready-probe") == "1"
        except Exception:
            logger.exception("Readiness: cache unavailable")
            return False
