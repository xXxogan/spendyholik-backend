"""Guards against N+1 regressions: query counts must not grow with the data."""

from __future__ import annotations

import pytest


def _account(client, currency="RUB"):
    return client.post(
        "/api/v1/accounts/",
        {"name": f"Счёт {currency}", "type": "debit", "currency": currency},
        format="json",
    ).json()["id"]


def _category(client, name, type_="expense"):
    return client.post("/api/v1/categories/", {"name": name, "type": type_}, format="json").json()[
        "id"
    ]


def _seed(client, n):
    account = _account(client)
    for i in range(n):
        category = _category(client, f"Категория {i}")
        client.post(
            "/api/v1/transactions/",
            {
                "account_id": account,
                "type": "expense",
                "amount_minor": 100_00,
                "date": "2026-03-10",
                "category_id": category,
            },
            format="json",
        )
        client.post(
            "/api/v1/budgets/", {"category_id": category, "amount_minor": 1000_00}, format="json"
        )
        client.post(
            "/api/v1/goals/",
            {
                "name": f"Цель {i}",
                "target_amount_minor": 1000_00,
                "currency": "RUB",
                "account_id": account,
            },
            format="json",
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "max_queries"),
    [("/api/v1/transactions/", 2), ("/api/v1/dashboard/", 7), ("/api/v1/goals/", 3)],
)
def test_list_endpoints_do_not_scale_with_rows(
    auth_client, django_assert_max_num_queries, path, max_queries
):
    # Each limit includes the auth user lookup.
    _seed(auth_client, 5)
    with django_assert_max_num_queries(max_queries):
        assert auth_client.get(path).status_code == 200


@pytest.mark.django_db
def test_transaction_view_carries_category_labels(auth_client):
    account = _account(auth_client)
    category = _category(auth_client, "Продукты")
    auth_client.post(
        "/api/v1/transactions/",
        {
            "account_id": account,
            "type": "expense",
            "amount_minor": 1240_00,
            "date": "2026-03-15",
            "category_id": category,
        },
        format="json",
    )
    item = auth_client.get("/api/v1/transactions/").json()["items"][0]
    assert item["title"] == "Продукты"
    assert item["account"]["name"] == "Счёт RUB"
    assert item["category"] == {
        "id": category,
        "name": "Продукты",
        "icon": "tag",
        "color": "default",
    }


@pytest.mark.django_db
def test_feed_is_ordered_by_transaction_date(auth_client):
    account = _account(auth_client)
    for day in ("2026-03-10", "2026-03-01", "2026-03-05"):
        auth_client.post(
            "/api/v1/transactions/",
            {"account_id": account, "type": "income", "amount_minor": 1, "date": day},
            format="json",
        )
    page1 = auth_client.get("/api/v1/transactions/?limit=2").json()
    page2 = auth_client.get(f"/api/v1/transactions/?limit=2&cursor={page1['next_cursor']}").json()
    dates = [t["date"] for t in page1["items"] + page2["items"]]
    assert dates == ["2026-03-10", "2026-03-05", "2026-03-01"]
    assert page2["next_cursor"] is None
