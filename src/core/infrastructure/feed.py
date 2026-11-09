"""Account feed: transactions plus the goal and debt events that move balances.

One ``UNION ALL`` over the four sources picks the page by (date, created_at,
id), newest first, with the same cursor format as ``GET /transactions/``;
then each kind is loaded in one query. Events stay out of analytics and
budgets — they only show up here.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db.models import CharField, F, Q, Value

from debts.domain.enums import DebtDirection
from debts.infrastructure.orm.models import Debt, DebtPayment
from finances.application.dto import AccountRefDTO, FeedItemDTO, FeedPageDTO
from finances.application.ports import FeedReader
from finances.application.use_cases import _transaction_dto
from finances.infrastructure.mappers import transaction_to_domain
from finances.infrastructure.orm.models import Account, Transaction
from finances.infrastructure.repositories import (
    _LABEL_RELATIONS,
    decode_cursor,
    encode_cursor,
    transaction_labels,
)
from goals.infrastructure.orm.models import GoalContribution
from shared.domain.money import Money

TRANSACTION = "transaction"
DEBT_OPENING = "debt_opening"
DEBT_PAYMENT = "debt_payment"
GOAL_CONTRIBUTION = "goal_contribution"


def _rows(qs, kind: str, date_field: str):
    """The common columns of every source, in the same order."""
    return (
        qs.order_by()
        .annotate(
            feed_kind=Value(kind, output_field=CharField()),
            feed_id=F("id"),
            feed_date=F(date_field),
            feed_at=F("created_at"),
        )
        .values_list("feed_kind", "feed_id", "feed_date", "feed_at")
    )


def _after(qs, date_field: str, cursor: str | None):
    if cursor is None:
        return qs
    day, created_at, pk = decode_cursor(cursor)
    return qs.filter(
        Q(**{f"{date_field}__lt": day})
        | Q(**{date_field: day, "created_at__lt": created_at})
        | Q(**{date_field: day, "created_at": created_at, "id__lt": pk})
    )


def _range(qs, date_field: str, date_from, date_to):
    if date_from is not None:
        qs = qs.filter(**{f"{date_field}__gte": date_from})
    if date_to is not None:
        qs = qs.filter(**{f"{date_field}__lte": date_to})
    return qs


class DjangoFeedReader(FeedReader):
    def page(
        self, user_id, *, account_id=None, date_from=None, date_to=None, cursor=None, limit=20
    ) -> FeedPageDTO:
        transactions = Transaction.objects.filter(user_id=user_id)
        openings = Debt.objects.filter(
            user_id=user_id, account__isnull=False, opened_on__isnull=False
        )
        payments = DebtPayment.objects.filter(debt__user_id=user_id, account__isnull=False)
        contributions = GoalContribution.objects.filter(
            goal__user_id=user_id, account__isnull=False
        )
        if account_id is not None:
            transactions = transactions.filter(
                Q(account_id=account_id) | Q(transfer_to_account_id=account_id)
            )
            openings = openings.filter(account_id=account_id)
            payments = payments.filter(account_id=account_id)
            contributions = contributions.filter(account_id=account_id)
        sources = [
            (transactions, TRANSACTION, "date"),
            (openings, DEBT_OPENING, "opened_on"),
            (payments, DEBT_PAYMENT, "date"),
            (contributions, GOAL_CONTRIBUTION, "date"),
        ]
        parts = [
            _rows(_after(_range(qs, field, date_from, date_to), field, cursor), kind, field)
            for qs, kind, field in sources
        ]
        union = parts[0].union(*parts[1:], all=True).order_by("-feed_date", "-feed_at", "-feed_id")
        rows = list(union[: limit + 1])
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            _, pk, day, created_at = rows[-1]
            next_cursor = encode_cursor(day, created_at, pk)
        return FeedPageDTO(items=self._hydrate(user_id, rows, account_id), next_cursor=next_cursor)

    def _hydrate(self, user_id, rows, account_id) -> list[FeedItemDTO]:
        ids: dict[str, list[UUID]] = {}
        for kind, pk, _, _ in rows:
            ids.setdefault(kind, []).append(pk)
        txs = Transaction.objects.select_related(*_LABEL_RELATIONS).in_bulk(
            ids.get(TRANSACTION, [])
        )
        debts = Debt.objects.in_bulk(ids.get(DEBT_OPENING, []))
        payments = DebtPayment.objects.select_related("debt").in_bulk(ids.get(DEBT_PAYMENT, []))
        contributions = GoalContribution.objects.select_related("goal").in_bulk(
            ids.get(GOAL_CONTRIBUTION, [])
        )
        accounts = {
            a.id: AccountRefDTO(id=a.id, name=a.name, color=a.color)
            for a in Account.objects.filter(user_id=user_id)
        }
        loaded = {
            TRANSACTION: txs,
            DEBT_OPENING: debts,
            DEBT_PAYMENT: payments,
            GOAL_CONTRIBUTION: contributions,
        }
        items = []
        for kind, pk, day, _ in rows:
            if pk not in loaded[kind]:
                continue  # deleted between the page query and loading it
            if kind == TRANSACTION:
                tx = txs[pk]
                if tx.type == "income":
                    effect = "in"
                elif tx.type == "expense":
                    effect = "out"
                elif account_id is None:
                    effect = "transfer"
                else:
                    effect = "in" if tx.transfer_to_account_id == account_id else "out"
                items.append(
                    FeedItemDTO(
                        kind=kind,
                        id=pk,
                        date=day,
                        amount=Money(Decimal(tx.amount), tx.account.currency),
                        effect=effect,
                        account=accounts.get(tx.account_id),
                        transaction=_transaction_dto(
                            transaction_to_domain(tx), transaction_labels(tx)
                        ),
                    )
                )
            elif kind == DEBT_OPENING:
                debt = debts[pk]
                items.append(
                    FeedItemDTO(
                        kind=kind,
                        id=pk,
                        date=day,
                        amount=Money(Decimal(debt.amount), debt.currency),
                        effect="in" if debt.direction == DebtDirection.I_OWE.value else "out",
                        account=accounts.get(debt.account_id),
                        debt=_debt_ref(debt),
                    )
                )
            elif kind == DEBT_PAYMENT:
                payment = payments[pk]
                items.append(
                    FeedItemDTO(
                        kind=kind,
                        id=pk,
                        date=day,
                        amount=Money(Decimal(payment.amount), payment.currency),
                        effect="out"
                        if payment.debt.direction == DebtDirection.I_OWE.value
                        else "in",
                        account=accounts.get(payment.account_id),
                        debt=_debt_ref(payment.debt),
                    )
                )
            else:
                contribution = contributions[pk]
                items.append(
                    FeedItemDTO(
                        kind=kind,
                        id=pk,
                        date=day,
                        amount=Money(Decimal(contribution.amount), contribution.currency),
                        effect="out",
                        account=accounts.get(contribution.account_id),
                        goal={"id": str(contribution.goal_id), "name": contribution.goal.name},
                    )
                )
        return items


def _debt_ref(debt: Debt) -> dict:
    return {"id": str(debt.id), "person_name": debt.person_name, "direction": debt.direction}
