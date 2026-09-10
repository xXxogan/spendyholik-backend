"""DRF views for the finances bounded context."""

from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, created, ok
from core.interfaces.deps import container
from core.interfaces.renderers import (
    account_to_view,
    budget_to_view,
    category_to_view,
    transaction_to_view,
)
from finances.application.dto import (
    CreateAccountInput,
    CreateBudgetInput,
    CreateCategoryInput,
    CreateTransactionInput,
    ListTransactionsInput,
    UpdateAccountInput,
    UpdateBudgetInput,
    UpdateCategoryInput,
    UpdateTransactionInput,
)


def _uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _names(accounts: list, categories: list) -> tuple[dict[UUID, str], dict[UUID, str]]:
    account_names = {a.id: a.name for a in accounts}
    category_names = {c.id: c.name for c in categories}
    return account_names, category_names


class AccountListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        include_archived = request.query_params.get("include_archived", "false").lower() == "true"
        return ok([account_to_view(a) for a in container.list_accounts().execute(request.user.id, include_archived=include_archived)])

    def post(self, request: Request):
        data = self.parse(CreateAccountInput, request.data)
        return created(account_to_view(container.create_account().execute(request.user.id, data)))


class AccountDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str):
        return ok(account_to_view(container.get_account_detail().execute(request.user.id, _uuid(pk))))

    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateAccountInput, request.data)
        return ok(account_to_view(container.update_account().execute(request.user.id, _uuid(pk), data)))

    def delete(self, request: Request, pk: str):
        container.archive_account().execute(request.user.id, _uuid(pk))
        return ok({"detail": "ok"})


class AccountArchiveView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: str):
        return ok(account_to_view(container.archive_account().execute(request.user.id, _uuid(pk))))


class CategoryListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([category_to_view(c) for c in container.list_categories().execute(request.user.id)])

    def post(self, request: Request):
        data = self.parse(CreateCategoryInput, request.data)
        return created(category_to_view(container.create_category().execute(request.user.id, data)))


class CategoryDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateCategoryInput, request.data)
        return ok(category_to_view(container.update_category().execute(request.user.id, _uuid(pk), data)))

    def delete(self, request: Request, pk: str):
        container.delete_category().execute(request.user.id, _uuid(pk))
        return ok({"detail": "ok"})


class TransactionListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        qp = request.query_params
        data = ListTransactionsInput(
            account_id=qp.get("account_id"),
            category_id=qp.get("category_id"),
            type=qp.get("type"),
            date_from=qp.get("date_from"),
            date_to=qp.get("date_to"),
            search=qp.get("search"),
            cursor=qp.get("cursor"),
            limit=qp.get("limit") or 20,
        )
        page = container.list_transactions().execute(request.user.id, data)
        accounts = container.list_accounts().execute(request.user.id, include_archived=True)
        categories = container.list_categories().execute(request.user.id)
        account_names, category_names = _names(accounts, categories)
        items = [
            transaction_to_view(
                t,
                account_name=account_names.get(t.account_id),
                category_name=category_names.get(t.category_id) if t.category_id else None,
            )
            for t in page.items
        ]
        return ok({"items": items, "next_cursor": page.next_cursor})

    def post(self, request: Request):
        data = self.parse(CreateTransactionInput, request.data)
        dto = container.create_transaction().execute(request.user.id, data)
        account = container.get_account_detail().execute(request.user.id, dto.account_id)
        category_name = None
        if dto.category_id:
            category_name = next(
                (c.name for c in container.list_categories().execute(request.user.id) if c.id == dto.category_id),
                None,
            )
        return created(transaction_to_view(dto, account_name=account.name, category_name=category_name))


class TransactionDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def _view(self, request: Request, pk: str):
        dto = container.get_transaction().execute(request.user.id, _uuid(pk))
        account = container.get_account_detail().execute(request.user.id, dto.account_id)
        category_name = None
        if dto.category_id:
            category_name = next(
                (c.name for c in container.list_categories().execute(request.user.id) if c.id == dto.category_id),
                None,
            )
        return transaction_to_view(dto, account_name=account.name, category_name=category_name)

    def get(self, request: Request, pk: str):
        return ok(self._view(request, pk))

    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateTransactionInput, request.data)
        dto = container.update_transaction().execute(request.user.id, _uuid(pk), data)
        return ok(self._view(request, pk))

    def delete(self, request: Request, pk: str):
        container.delete_transaction().execute(request.user.id, _uuid(pk))
        return ok({"detail": "ok"})


class BudgetListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([budget_to_view(b) for b in container.list_budgets().execute(request.user.id)])

    def post(self, request: Request):
        data = self.parse(CreateBudgetInput, request.data)
        return created(budget_to_view(container.create_budget().execute(request.user.id, data)))


class BudgetDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str):
        return ok(budget_to_view(container.get_budget_detail().execute(request.user.id, _uuid(pk))))

    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateBudgetInput, request.data)
        return ok(budget_to_view(container.update_budget().execute(request.user.id, _uuid(pk), data)))

    def delete(self, request: Request, pk: str):
        container.delete_budget().execute(request.user.id, _uuid(pk))
        return ok({"detail": "ok"})
