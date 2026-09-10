"""Health / readiness views (k8s probes)."""

from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from core.interfaces.api import BaseAPIView, ok


class HealthView(BaseAPIView):
    permission_classes = [AllowAny]

    def get(self, request: Request):
        return ok({"status": "ok"})


class ReadyView(BaseAPIView):
    permission_classes = [AllowAny]

    def get(self, request: Request):
        try:
            connection.ensure_connection()
            return ok({"status": "ready"})
        except Exception:
            return Response({"status": "not_ready"}, status=503)
