"""R-03: the OpenAPI schema documents responses, query parameters and request bodies."""

from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def _operation(schema, path, method):
    return schema["paths"][f"/api/v1/{path}"][method]


def test_schema_is_valid_openapi(schema):
    validate_schema(schema)


@pytest.mark.parametrize(
    ("path", "method", "status", "component"),
    [
        ("accounts/", "get", "200", "AccountOutList"),
        ("accounts/{id}/balance-history/", "get", "200", "BalancePointOutList"),
        ("transactions/", "get", "200", "TransactionPageOut"),
        ("budgets/{id}/", "get", "200", "BudgetOut"),
        ("goals/", "post", "201", "GoalOut"),
        ("goals/{id}/contributions/", "get", "200", "ContributionOutList"),
        ("debts/{id}/history/", "get", "200", "DebtEventOutList"),
        ("recurring/", "get", "200", "RecurringOutList"),
        ("analytics/trend/", "get", "200", "TrendPointOutList"),
        ("notifications/", "get", "200", "NotificationOutList"),
        ("profile/", "get", "200", "ProfileOut"),
    ],
)
def test_responses_are_documented(schema, path, method, status, component):
    response = _operation(schema, path, method)["responses"][status]
    ref = response["content"]["application/json"]["schema"]["$ref"]
    assert ref == f"#/components/schemas/{component}"


def test_errors_are_documented(schema):
    responses = _operation(schema, "goals/{id}/contribute/", "post")["responses"]
    assert responses["409"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorOut")


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("transactions/", {"account_id", "category_id", "type", "date_from", "date_to", "cursor"}),
        ("analytics/trend/", {"granularity", "date_from", "date_to"}),
        ("accounts/", {"include_archived"}),
        ("accounts/{id}/balance-history/", {"weeks"}),
    ],
)
def test_query_parameters_are_documented(schema, path, params):
    documented = {p["name"] for p in _operation(schema, path, "get").get("parameters", [])}
    assert params <= documented


@pytest.mark.parametrize(
    ("path", "method"),
    [("goals/", "post"), ("debts/{id}/", "patch"), ("recurring/", "post"), ("profile/", "patch")],
)
def test_request_bodies_are_documented(schema, path, method):
    assert "requestBody" in _operation(schema, path, method)


def test_account_schema_has_the_balance(schema):
    assert "balance" in schema["components"]["schemas"]["AccountOut"]["properties"]
