"""API for BK-1…BK-4 (contracts.md, phase 2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command

from finances.infrastructure.orm.models import ExchangeRate
from shared.application.ports import RatesSnapshot
from shared.exceptions import ExchangeRatesUnavailableError

pytestmark = pytest.mark.django_db


def _account(client, name="Карта", currency="RUB", initial=0):
    return client.post(
        "/api/v1/accounts/",
        {"name": name, "type": "debit", "currency": currency, "initial_balance_minor": initial},
        format="json",
    ).json()


def _category(client, name="Еда"):
    return client.post(
        "/api/v1/categories/", {"name": name, "type": "expense"}, format="json"
    ).json()


def _tx(client, **data):
    body = {"type": "expense", "amount_minor": 10_00, "date": "2026-11-07"} | data
    return client.post("/api/v1/transactions/", body, format="json")


class TestTitle:
    def test_given_title_is_stored_and_searchable(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client)
        resp = _tx(auth_client, account_id=card["id"], category_id=food["id"], title=" Пятёрочка ")
        assert resp.status_code == 201
        assert resp.json()["title"] == "Пятёрочка"
        # Same case: SQLite's LIKE folds ASCII only (PostgreSQL folds Cyrillic too).
        found = auth_client.get("/api/v1/transactions/?search=Пятёр").json()["items"]
        assert [t["id"] for t in found] == [resp.json()["id"]]

    def test_empty_title_falls_back_to_the_category(self, auth_client):
        card = _account(auth_client)
        food = _category(auth_client)
        tx = _tx(auth_client, account_id=card["id"], category_id=food["id"]).json()
        assert tx["title"] == "Еда"
        renamed = auth_client.patch(
            f"/api/v1/transactions/{tx['id']}/", {"title": "Обед"}, format="json"
        ).json()
        assert renamed["title"] == "Обед"
        cleared = auth_client.patch(
            f"/api/v1/transactions/{tx['id']}/", {"title": ""}, format="json"
        ).json()
        assert cleared["title"] == "Еда"

    def test_title_length_is_limited(self, auth_client):
        card = _account(auth_client)
        resp = _tx(auth_client, account_id=card["id"], title="x" * 121)
        assert resp.json()["errors"] == {"title": "too_long"}


def test_account_filter_includes_incoming_transfers(auth_client):
    card = _account(auth_client, initial=1000_00)
    cash = _account(auth_client, name="Наличные")
    incoming = _tx(
        auth_client, account_id=card["id"], type="transfer", transfer_to_account_id=cash["id"]
    ).json()
    own = _tx(auth_client, account_id=cash["id"]).json()
    _tx(auth_client, account_id=card["id"])
    items = auth_client.get(f"/api/v1/transactions/?account_id={cash['id']}").json()["items"]
    assert {t["id"] for t in items} == {incoming["id"], own["id"]}


def test_cross_currency_transfer_is_a_field_error(auth_client):
    rub = _account(auth_client)
    usd = _account(auth_client, name="USD", currency="USD")
    resp = _tx(auth_client, account_id=rub["id"], type="transfer", transfer_to_account_id=usd["id"])
    assert resp.status_code == 422
    assert resp.json()["code"] == "currency_mismatch"
    assert resp.json()["errors"] == {"transfer_to_account_id": "currency_mismatch"}


class TestExchangeRates:
    _PROVIDER = "shared.infrastructure.gateways.OpenErApiExchangeRateProvider.latest"

    def test_command_stores_rates_and_totals_use_them(self, auth_client):
        snapshot = RatesSnapshot("USD", date(2026, 11, 7), {"RUB": Decimal("80")})
        with mock.patch(self._PROVIDER, return_value=snapshot):
            out = StringIO()
            call_command("refresh_exchange_rates", stdout=out)
        assert "updated 1" in out.getvalue()
        assert ExchangeRate.objects.get(base="USD", target="RUB").rate == Decimal("80")
        _account(auth_client, initial=1000_00)
        _account(auth_client, name="USD", currency="USD", initial=10_00)
        dashboard = auth_client.get("/api/v1/dashboard/").json()
        assert dashboard["total_balance"]["minor"] == 1800_00
        assert dashboard["excluded_currencies"] == []

    def test_unavailable_provider_fails_the_command(self):
        error = ExchangeRatesUnavailableError("timeout")
        with mock.patch(self._PROVIDER, side_effect=error), pytest.raises(CommandError):
            call_command("refresh_exchange_rates")
