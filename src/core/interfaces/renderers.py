"""Render domain DTOs into flat ViewModels ready for client binding.

Money is rendered as ``{"minor": int, "currency": str, "formatted": str}``.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Any

from shared.domain.money import Money

CURRENCY_SYMBOLS = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "KZT": "₸",
    "UAH": "₴",
}

MINUS = "\u2212"  # U+2212 minus sign


def format_money(money: Money) -> str:
    symbol = CURRENCY_SYMBOLS.get(money.currency, money.currency)
    value = money.amount
    sign = ""
    if value < 0:
        sign = MINUS
        value = -value
    text = f"{value:,.2f}".replace(",", "\u00a0")  # thousands separator = no-break space
    if text.endswith(".00"):
        text = text[:-3]
    return f"{sign}{text} {symbol}".strip()


def money_to_view(money: Money) -> dict[str, Any]:
    return {
        "minor": money.to_minor_units(),
        "currency": money.currency,
        "formatted": format_money(money),
    }


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _iso_time(value: time | None) -> str | None:
    return value.isoformat() if value else None


def account_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "name": dto.name,
        "type": dto.type.value,
        "currency": dto.currency,
        "initial_balance": money_to_view(dto.initial_balance),
        "color": dto.color,
        "last4": dto.last4,
        "credit_limit": money_to_view(dto.credit_limit) if dto.credit_limit is not None else None,
        "interest_rate": str(dto.interest_rate),
        "is_archived": dto.is_archived,
    }


def category_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "name": dto.name,
        "type": dto.type.value,
        "icon": dto.icon,
        "color": dto.color,
        "parent_id": str(dto.parent_id) if dto.parent_id else None,
        "is_system": dto.is_system,
    }


def transaction_to_view(dto) -> dict[str, Any]:
    labels = dto.labels
    account_name = labels.account_name if labels else None
    category_name = labels.category_name if labels else None
    is_transfer = dto.type.value == "transfer"
    title = (account_name or "Перевод") if is_transfer else (category_name or "")
    return {
        "id": str(dto.id),
        "type": dto.type.value,
        "amount": money_to_view(dto.amount),
        "title": title,
        "subtitle": account_name or "",
        "category": {
            "id": str(dto.category_id),
            "name": category_name,
            "icon": labels.category_icon if labels else None,
            "color": labels.category_color if labels else None,
        }
        if dto.category_id
        else None,
        "account": {"id": str(dto.account_id), "name": account_name},
        "date": _iso_date(dto.date),
        "time": _iso_time(dto.time),
        "note": dto.note,
        "receipt": {"id": str(dto.receipt_id)} if dto.receipt_id else None,
        "transfer_to_account_id": str(dto.transfer_to_account_id)
        if dto.transfer_to_account_id
        else None,
    }


def budget_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "category_id": str(dto.category_id),
        "amount": money_to_view(dto.amount),
        "period": dto.period.value,
        "start_date": _iso_date(dto.start_date),
        "is_active": dto.is_active,
    }


def goal_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "name": dto.name,
        "target_amount": money_to_view(dto.target_amount),
        "current_amount": money_to_view(dto.current_amount),
        "account_id": str(dto.account_id),
        "deadline": _iso_date(dto.deadline),
        "icon": dto.icon,
        "color": dto.color,
        "progress": dto.progress,
    }


def debt_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "person_name": dto.person_name,
        "direction": dto.direction.value,
        "amount": money_to_view(dto.amount),
        "remaining": money_to_view(dto.remaining),
        "due_date": _iso_date(dto.due_date),
        "is_closed": dto.is_closed,
    }


def notification_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "type": dto.type.value,
        "title": dto.title,
        "body": dto.body,
        "is_read": dto.is_read,
    }


def recurring_to_view(dto) -> dict[str, Any]:
    return {
        "id": str(dto.id),
        "name": dto.name,
        "amount": money_to_view(dto.amount),
        "type": dto.type.value,
        "account_id": str(dto.account_id),
        "category_id": str(dto.category_id) if dto.category_id else None,
        "frequency": dto.frequency.value,
        "next_run": _iso_date(dto.next_run),
        "is_active": dto.is_active,
    }


def dashboard_to_view(dto) -> dict[str, Any]:
    return {
        "total_balance": money_to_view(dto.total_balance),
        "income_this_month": money_to_view(dto.income_this_month),
        "expense_this_month": money_to_view(dto.expense_this_month),
        "net_this_month": money_to_view(dto.net_this_month),
        "budgets": [
            {
                "budget_id": str(b.budget_id),
                "category_id": str(b.category_id),
                "limit": money_to_view(b.limit),
                "spent": money_to_view(b.spent),
                "remaining": money_to_view(b.remaining),
                "ratio": b.ratio,
            }
            for b in dto.budgets
        ],
        "excluded_currencies": dto.excluded_currencies,
    }


def _as_decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))
