"""DRF views for the finances bounded context."""

from __future__ import annotations

from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, created, no_content, ok
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


class AccountListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        include_archived = request.query_params.get("include_archived", "false").lower() == "true"
        return ok(
            [
                account_to_view(a)
                for a in container.list_accounts().execute(
                    request.user.id, include_archived=include_archived
                )
            ]
        )

    @extend_schema(request=CreateAccountInput)
    def post(self, request: Request):
        data = self.parse(CreateAccountInput, request.data)
        return created(account_to_view(container.create_account().execute(request.user.id, data)))


class AccountDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str):
        return ok(
            account_to_view(container.get_account_detail().execute(request.user.id, _uuid(pk)))
        )

    @extend_schema(request=UpdateAccountInput)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateAccountInput, request.data)
        return ok(
            account_to_view(container.update_account().execute(request.user.id, _uuid(pk), data))
        )

    def delete(self, request: Request, pk: str):
        container.archive_account().execute(request.user.id, _uuid(pk))
        return no_content()


class AccountArchiveView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: str):
        return ok(account_to_view(container.archive_account().execute(request.user.id, _uuid(pk))))


class CategoryListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok(
            [category_to_view(c) for c in container.list_categories().execute(request.user.id)]
        )

    @extend_schema(request=CreateCategoryInput)
    def post(self, request: Request):
        data = self.parse(CreateCategoryInput, request.data)
        return created(category_to_view(container.create_category().execute(request.user.id, data)))


class CategoryDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=UpdateCategoryInput)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateCategoryInput, request.data)
        return ok(
            category_to_view(container.update_category().execute(request.user.id, _uuid(pk), data))
        )

    def delete(self, request: Request, pk: str):
        container.delete_category().execute(request.user.id, _uuid(pk))
        return no_content()


class TransactionListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        fields = ListTransactionsInput.model_fields
        data = self.parse(
            ListTransactionsInput,
            {k: v for k, v in request.query_params.items() if k in fields and v != ""},
        )
        page = container.list_transactions().execute(request.user.id, data)
        return ok(
            {
                "items": [transaction_to_view(t) for t in page.items],
                "next_cursor": page.next_cursor,
            }
        )

    @extend_schema(request=CreateTransactionInput)
    def post(self, request: Request):
        data = self.parse(CreateTransactionInput, request.data)
        dto = container.create_transaction().execute(request.user.id, data)
        # Re-read through the labelled query to render account/category names.
        return created(
            transaction_to_view(container.get_transaction().execute(request.user.id, dto.id))
        )


class TransactionDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str):
        return ok(
            transaction_to_view(container.get_transaction().execute(request.user.id, _uuid(pk)))
        )

    @extend_schema(request=UpdateTransactionInput)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateTransactionInput, request.data)
        container.update_transaction().execute(request.user.id, _uuid(pk), data)
        return ok(
            transaction_to_view(container.get_transaction().execute(request.user.id, _uuid(pk)))
        )

    def delete(self, request: Request, pk: str):
        container.delete_transaction().execute(request.user.id, _uuid(pk))
        return no_content()


class BudgetListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([budget_to_view(b) for b in container.list_budgets().execute(request.user.id)])

    @extend_schema(request=CreateBudgetInput)
    def post(self, request: Request):
        data = self.parse(CreateBudgetInput, request.data)
        return created(budget_to_view(container.create_budget().execute(request.user.id, data)))


class BudgetDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str):
        return ok(budget_to_view(container.get_budget_detail().execute(request.user.id, _uuid(pk))))

    @extend_schema(request=UpdateBudgetInput)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateBudgetInput, request.data)
        return ok(
            budget_to_view(container.update_budget().execute(request.user.id, _uuid(pk), data))
        )

    def delete(self, request: Request, pk: str):
        container.delete_budget().execute(request.user.id, _uuid(pk))
        return no_content()
