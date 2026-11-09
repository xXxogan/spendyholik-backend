"""B-18: debt openings move an account; the feed shows transactions with events."""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.django_db


def _account(client, initial=0, name="Карта", currency="RUB"):
    return client.post(
        "/api/v1/accounts/",
        {"name": name, "type": "debit", "currency": currency, "initial_balance_minor": initial},
        format="json",
    ).json()


def _balance(client, account_id) -> int:
    return client.get(f"/api/v1/accounts/{account_id}/").json()["balance"]["minor"]


def _debt(client, direction, amount, account_id=None, on="2026-03-01"):
    body = {
        "person_name": "Иван",
        "direction": direction,
        "amount_minor": amount,
        "currency": "RUB",
        "date": on,
    }
    if account_id:
        body["account_id"] = account_id
    return client.post("/api/v1/debts/", body, format="json")


class TestDebtOpening:
    def test_borrowed_money_comes_in_and_lent_money_goes_out(self, auth_client):
        card = _account(auth_client, 1000_00)
        borrowed = _debt(auth_client, "i_owe", 500_00, card["id"])
        assert borrowed.status_code == 201
        assert borrowed.json()["account_id"] == card["id"]
        assert borrowed.json()["opened_on"] == "2026-03-01"
        assert _balance(auth_client, card["id"]) == 1500_00
        assert _debt(auth_client, "owed_to_me", 300_00, card["id"]).status_code == 201
        assert _balance(auth_client, card["id"]) == 1200_00

    def test_lending_needs_funds(self, auth_client):
        card = _account(auth_client, 100_00)
        resp = _debt(auth_client, "owed_to_me", 300_00, card["id"])
        assert resp.status_code == 409
        assert resp.json()["errors"] == {"amount_minor": "insufficient_funds"}

    def test_account_currency_must_match(self, auth_client):
        usd = _account(auth_client, currency="USD")
        resp = _debt(auth_client, "i_owe", 100_00, usd["id"])
        assert resp.json()["errors"] == {"account_id": "currency_mismatch"}

    def test_without_an_account_nothing_moves(self, auth_client):
        card = _account(auth_client, 1000_00)
        _debt(auth_client, "i_owe", 500_00)
        assert _balance(auth_client, card["id"]) == 1000_00

    def test_editing_the_amount_moves_the_opening(self, auth_client):
        card = _account(auth_client, 1000_00)
        debt = _debt(auth_client, "i_owe", 500_00, card["id"]).json()
        auth_client.patch(f"/api/v1/debts/{debt['id']}/", {"amount_minor": 700_00}, format="json")
        assert _balance(auth_client, card["id"]) == 1700_00

    def test_history_names_the_opening_account(self, auth_client):
        card = _account(auth_client, 1000_00)
        debt = _debt(auth_client, "i_owe", 500_00, card["id"]).json()
        [opened] = auth_client.get(f"/api/v1/debts/{debt['id']}/history/").json()
        assert (opened["kind"], opened["date"], opened["account"]["id"]) == (
            "opened",
            "2026-03-01",
            card["id"],
        )


class TestFeed:
    def _world(self, client):
        card = _account(client, 10000_00)
        cash = _account(client, 0, name="Наличные")
        client.post(
            "/api/v1/transactions/",
            {
                "account_id": card["id"],
                "type": "expense",
                "amount_minor": 100_00,
                "date": "2026-03-05",
            },
            format="json",
        )
        client.post(
            "/api/v1/transactions/",
            {
                "account_id": card["id"],
                "type": "transfer",
                "amount_minor": 200_00,
                "date": "2026-03-04",
                "transfer_to_account_id": cash["id"],
            },
            format="json",
        )
        debt = _debt(client, "i_owe", 500_00, card["id"], on="2026-03-03").json()
        client.post(
            f"/api/v1/debts/{debt['id']}/repay/",
            {"account_id": card["id"], "amount_minor": 50_00, "date": "2026-03-06"},
            format="json",
        )
        goal = client.post(
            "/api/v1/goals/",
            {"name": "Отпуск", "target_amount_minor": 1000_00, "currency": "RUB"},
            format="json",
        ).json()
        client.post(
            f"/api/v1/goals/{goal['id']}/contribute/",
            {"account_id": card["id"], "amount_minor": 70_00, "date": "2026-03-07"},
            format="json",
        )
        return card, cash, debt, goal

    def test_events_and_transactions_newest_first(self, auth_client):
        card, _, debt, goal = self._world(auth_client)
        items = auth_client.get(f"/api/v1/feed/?account_id={card['id']}").json()["items"]
        assert [(i["kind"], i["date"], i["effect"], i["amount"]["minor"]) for i in items] == [
            ("goal_contribution", "2026-03-07", "out", 70_00),
            ("debt_payment", "2026-03-06", "out", 50_00),
            ("transaction", "2026-03-05", "out", 100_00),
            ("transaction", "2026-03-04", "out", 200_00),
            ("debt_opening", "2026-03-03", "in", 500_00),
        ]
        assert items[0]["goal"] == {"id": goal["id"], "name": "Отпуск"}
        assert items[1]["debt"] == {"id": debt["id"], "person_name": "Иван", "direction": "i_owe"}
        assert items[2]["transaction"]["amount"]["minor"] == 100_00
        assert items[4]["transaction"] is None

    def test_incoming_transfer_is_in_for_the_destination(self, auth_client):
        _, cash, _, _ = self._world(auth_client)
        items = auth_client.get(f"/api/v1/feed/?account_id={cash['id']}").json()["items"]
        assert [(i["kind"], i["effect"]) for i in items] == [("transaction", "in")]

    def test_pages_share_one_cursor(self, auth_client):
        card, _, _, _ = self._world(auth_client)
        seen = []
        url = f"/api/v1/feed/?account_id={card['id']}&limit=2"
        while url:
            page = auth_client.get(url).json()
            seen += [i["kind"] for i in page["items"]]
            cursor = page["next_cursor"]
            url = (
                f"/api/v1/feed/?account_id={card['id']}&limit=2&cursor={cursor}" if cursor else None
            )
        assert seen == [
            "goal_contribution",
            "debt_payment",
            "transaction",
            "transaction",
            "debt_opening",
        ]

    def test_date_range_and_no_events_in_transactions(self, auth_client):
        self._world(auth_client)
        items = auth_client.get("/api/v1/feed/?date_from=2026-03-04&date_to=2026-03-05").json()
        assert [(i["kind"], i["effect"]) for i in items["items"]] == [
            ("transaction", "out"),
            ("transaction", "transfer"),
        ]
        assert len(auth_client.get("/api/v1/transactions/").json()["items"]) == 2


class TestDebtChangesNeedFunds:
    def _spent_loan(self, client):
        card = _account(client, 0)
        debt = _debt(client, "i_owe", 1000_00, card["id"]).json()
        client.post(
            "/api/v1/transactions/",
            {
                "account_id": card["id"],
                "type": "expense",
                "amount_minor": 900_00,
                "date": "2026-03-02",
            },
            format="json",
        )
        return card, debt

    def test_owing_less_of_a_spent_loan_needs_funds(self, auth_client):
        card, debt = self._spent_loan(auth_client)
        resp = auth_client.patch(
            f"/api/v1/debts/{debt['id']}/", {"amount_minor": 100_00}, format="json"
        )
        assert resp.status_code == 409
        assert resp.json()["errors"] == {"amount_minor": "insufficient_funds"}
        assert _balance(auth_client, card["id"]) == 100_00

    def test_deleting_a_spent_loan_needs_funds(self, auth_client):
        card, debt = self._spent_loan(auth_client)
        resp = auth_client.delete(f"/api/v1/debts/{debt['id']}/")
        assert resp.status_code == 409
        assert _balance(auth_client, card["id"]) == 100_00

    def test_deleting_after_repaying_returns_to_the_start(self, auth_client):
        card = _account(auth_client, 0)
        debt = _debt(auth_client, "i_owe", 1000_00, card["id"]).json()
        auth_client.post(
            f"/api/v1/debts/{debt['id']}/repay/",
            {"account_id": card["id"], "amount_minor": 1000_00, "date": "2026-03-05"},
            format="json",
        )
        assert auth_client.delete(f"/api/v1/debts/{debt['id']}/").status_code == 204
        assert _balance(auth_client, card["id"]) == 0

    def test_deleting_a_received_repayment_needs_funds(self, auth_client):
        card = _account(auth_client, 0)
        debt = _debt(auth_client, "owed_to_me", 500_00).json()  # lent in cash, no account
        auth_client.post(
            f"/api/v1/debts/{debt['id']}/repay/",
            {"account_id": card["id"], "amount_minor": 500_00, "date": "2026-03-05"},
            format="json",
        )
        auth_client.post(
            "/api/v1/transactions/",
            {
                "account_id": card["id"],
                "type": "expense",
                "amount_minor": 400_00,
                "date": "2026-03-06",
            },
            format="json",
        )
        assert auth_client.delete(f"/api/v1/debts/{debt['id']}/").status_code == 409


def test_row_deleted_while_loading_the_page_is_skipped(auth_client, user):
    from uuid import uuid4

    from core.infrastructure.feed import TRANSACTION, DjangoFeedReader

    rows = [(TRANSACTION, uuid4(), date(2026, 3, 1), None)]
    assert DjangoFeedReader()._hydrate(user.id, rows, None) == []
