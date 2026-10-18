"""Regression tests: bad input yields the unified 4xx error shape, never a 500."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestErrorShape:
    @pytest.mark.parametrize(
        "query",
        ["cursor=not-a-cursor", "limit=abc", "limit=1000", "type=gift", "date_from=yesterday"],
    )
    def test_bad_transaction_filters_are_422(self, auth_client, query):
        resp = auth_client.get(f"/api/v1/transactions/?{query}")
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"

    def test_validation_errors_are_keyed_by_field(self, auth_client):
        resp = auth_client.post("/api/v1/accounts/", {"type": "debit"}, format="json")
        assert resp.status_code == 422
        assert set(resp.json()["errors"]) == {"name", "currency"}

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/analytics/summary/?date_from=2026-13-01", "/api/v1/analytics/monthly/?months=x"],
    )
    def test_bad_analytics_params_are_422(self, auth_client, path):
        assert auth_client.get(path).status_code == 422

    def test_unauthenticated_has_its_own_code(self, api_client):
        resp = api_client.get("/api/v1/accounts/")
        assert resp.status_code == 401
        assert resp.json()["code"] == "not_authenticated"

    def test_method_not_allowed_code(self, auth_client):
        resp = auth_client.put("/api/v1/dashboard/", {}, format="json")
        assert resp.status_code == 405
        assert resp.json()["code"] == "method_not_allowed"


@pytest.mark.django_db
class TestProbes:
    def test_probes_ignore_bad_authorization_header(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        assert api_client.get("/health/").status_code == 200
        resp = api_client.get("/ready/")
        assert resp.status_code == 200
        assert resp.json()["checks"] == {"database": True, "cache": True}
