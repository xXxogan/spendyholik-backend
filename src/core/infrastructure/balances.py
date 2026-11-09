"""Account balances across bounded contexts.

Lives in ``core`` because a balance is moved by finances transactions, goal
contributions, debt openings and repayments alike; one query per source, grouped by
account (and by day for the history).
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db.models import Case, DecimalField, F, Q, Sum, When

from debts.domain.enums import DebtDirection
from debts.infrastructure.orm.models import Debt, DebtPayment
from finances.application.ports import BalanceReader
from finances.domain.enums import TransactionType
from finances.infrastructure.orm.models import Transaction
from goals.infrastructure.orm.models import GoalContribution

_MONEY = DecimalField(max_digits=16, decimal_places=2)


def _signed(when_negative: Q) -> Case:
    return Case(When(when_negative, then=-F("amount")), default=F("amount"), output_field=_MONEY)


class DjangoBalanceReader(BalanceReader):
    def _sources(self, user_id: UUID, account_ids: Collection[UUID] | None):
        """``(queryset, account field, signed amount)`` for every balance source."""
        own = Transaction.objects.filter(user_id=user_id)
        incoming = own.filter(type=TransactionType.TRANSFER.value)
        contributions = GoalContribution.objects.filter(goal__user_id=user_id)
        payments = DebtPayment.objects.filter(debt__user_id=user_id)
        # The opening of a debt tied to an account, dated by ``opened_on``.
        openings = Debt.objects.filter(user_id=user_id, opened_on__isnull=False).alias(
            date=F("opened_on")
        )
        if account_ids is not None:
            ids = list(account_ids)
            own = own.filter(account_id__in=ids)
            incoming = incoming.filter(transfer_to_account_id__in=ids)
            contributions = contributions.filter(account_id__in=ids)
            payments = payments.filter(account_id__in=ids)
            openings = openings.filter(account_id__in=ids)
        return [
            # Income adds; expenses and the outgoing leg of a transfer subtract.
            (own, "account_id", _signed(~Q(type=TransactionType.INCOME.value))),
            (incoming, "transfer_to_account_id", F("amount")),
            (contributions, "account_id", -F("amount")),
            (payments, "account_id", _signed(Q(debt__direction=DebtDirection.I_OWE.value))),
            # Borrowed money comes in; lent money goes out.
            (openings, "account_id", _signed(Q(direction=DebtDirection.OWED_TO_ME.value))),
        ]

    def deltas(self, user_id, account_ids=None, *, before=None):
        if account_ids is not None and not account_ids:
            return {}
        result: dict[UUID, Decimal] = {}
        for qs, account_field, amount in self._sources(user_id, account_ids):
            if before is not None:
                qs = qs.filter(date__lt=before)
            rows = (
                qs.exclude(**{f"{account_field}__isnull": True})
                .order_by()
                .values(account_field)
                .annotate(total=Sum(amount, output_field=_MONEY))
            )
            for row in rows:
                key = row[account_field]
                result[key] = result.get(key, Decimal(0)) + Decimal(row["total"] or 0)
        return result

    def daily_deltas(self, user_id, account_id, date_from: date, date_to: date):
        result: dict[date, Decimal] = {}
        for qs, _, amount in self._sources(user_id, [account_id]):
            rows = (
                qs.filter(date__gte=date_from, date__lte=date_to)
                .order_by()
                .annotate(day=F("date"))
                .values("day")
                .annotate(total=Sum(amount, output_field=_MONEY))
            )
            for row in rows:
                day = row["day"]
                result[day] = result.get(day, Decimal(0)) + Decimal(row["total"] or 0)
        return {day: total for day, total in result.items() if total}
