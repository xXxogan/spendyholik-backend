"""DRF views for the finances bounded context."""

from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces import schemas as sc
from core.interfaces.api import BaseAPIView, created, no_content, ok, query_int
from core.interfaces.deps import container
from core.interfaces.renderers import (
    account_to_view,
    balance_point_to_view,
    budget_to_view,
    category_to_view,
    transaction_to_view,
)
from core.interfaces.schemas import api_doc, many
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

    @api_doc(
        many(sc.AccountOut), parameters=sc.INCLUDE_ARCHIVED, operation_id="api_v1_accounts_list"
    )
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

    @api_doc(sc.AccountOut, request=CreateAccountInput, status=201, errors=sc.WRITE)
    def post(self, request: Request):
        data = self.parse(CreateAccountInput, request.data)
        return created(account_to_view(container.create_account().execute(request.user.id, data)))


class AccountDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.AccountOut, errors=sc.READ)
    def get(self, request: Request, pk: str):
        return ok(
            account_to_view(container.get_account_detail().execute(request.user.id, _uuid(pk)))
        )

    @api_doc(sc.AccountOut, request=UpdateAccountInput, errors=sc.WRITE)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateAccountInput, request.data)
        return ok(
            account_to_view(container.update_account().execute(request.user.id, _uuid(pk), data))
        )

    @api_doc(None, status=204, errors=sc.READ, description="Archives the account.")
    def delete(self, request: Request, pk: str):
        container.archive_account().execute(request.user.id, _uuid(pk))
        return no_content()


class AccountArchiveView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.AccountOut, request=None, errors=sc.READ)
    def post(self, request: Request, pk: str):
        return ok(account_to_view(container.archive_account().execute(request.user.id, _uuid(pk))))


class AccountUnarchiveView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.AccountOut, request=None, errors=sc.READ)
    def post(self, request: Request, pk: str):
        return ok(
            account_to_view(container.unarchive_account().execute(request.user.id, _uuid(pk)))
        )


class AccountBalanceHistoryView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(
        many(sc.BalancePointOut),
        parameters=sc.WEEKS,
        errors=(401, 404, 422),
        description=(
            "Balance before the window, after each day with movements, and today; ascending."
        ),
    )
    def get(self, request: Request, pk: str):
        weeks = query_int(request, "weeks", 6)
        points = container.get_balance_history().execute(request.user.id, _uuid(pk), weeks)
        return ok([balance_point_to_view(p) for p in points])


class CategoryListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(many(sc.CategoryOut))
    def get(self, request: Request):
        return ok(
            [category_to_view(c) for c in container.list_categories().execute(request.user.id)]
        )

    @api_doc(sc.CategoryOut, request=CreateCategoryInput, status=201, errors=sc.WRITE)
    def post(self, request: Request):
        data = self.parse(CreateCategoryInput, request.data)
        return created(category_to_view(container.create_category().execute(request.user.id, data)))


class CategoryDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.CategoryOut, request=UpdateCategoryInput, errors=sc.WRITE)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateCategoryInput, request.data)
        return ok(
            category_to_view(container.update_category().execute(request.user.id, _uuid(pk), data))
        )

    @api_doc(None, status=204, errors=(401, 404, 409))
    def delete(self, request: Request, pk: str):
        container.delete_category().execute(request.user.id, _uuid(pk))
        return no_content()


class TransactionListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(
        sc.TransactionPageOut,
        parameters=sc.TRANSACTION_FILTERS,
        operation_id="api_v1_transactions_list",
        errors=(401, 422),
    )
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

    @api_doc(sc.TransactionOut, request=CreateTransactionInput, status=201, errors=sc.WRITE)
    def post(self, request: Request):
        data = self.parse(CreateTransactionInput, request.data)
        dto = container.create_transaction().execute(request.user.id, data)
        # Re-read through the labelled query to render account/category names.
        return created(
            transaction_to_view(container.get_transaction().execute(request.user.id, dto.id))
        )


class TransactionDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.TransactionOut, errors=sc.READ)
    def get(self, request: Request, pk: str):
        return ok(
            transaction_to_view(container.get_transaction().execute(request.user.id, _uuid(pk)))
        )

    @api_doc(sc.TransactionOut, request=UpdateTransactionInput, errors=sc.WRITE)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateTransactionInput, request.data)
        container.update_transaction().execute(request.user.id, _uuid(pk), data)
        return ok(
            transaction_to_view(container.get_transaction().execute(request.user.id, _uuid(pk)))
        )

    @api_doc(None, status=204, errors=sc.READ)
    def delete(self, request: Request, pk: str):
        container.delete_transaction().execute(request.user.id, _uuid(pk))
        return no_content()


class BudgetListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(many(sc.BudgetOut), operation_id="api_v1_budgets_list")
    def get(self, request: Request):
        return ok([budget_to_view(b) for b in container.list_budgets().execute(request.user.id)])

    @api_doc(sc.BudgetOut, request=CreateBudgetInput, status=201, errors=sc.WRITE)
    def post(self, request: Request):
        data = self.parse(CreateBudgetInput, request.data)
        return created(budget_to_view(container.create_budget().execute(request.user.id, data)))


class BudgetDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.BudgetOut, errors=sc.READ)
    def get(self, request: Request, pk: str):
        return ok(budget_to_view(container.get_budget_detail().execute(request.user.id, _uuid(pk))))

    @api_doc(sc.BudgetOut, request=UpdateBudgetInput, errors=sc.WRITE)
    def patch(self, request: Request, pk: str):
        data = self.parse(UpdateBudgetInput, request.data)
        return ok(
            budget_to_view(container.update_budget().execute(request.user.id, _uuid(pk), data))
        )

    @api_doc(None, status=204, errors=sc.READ)
    def delete(self, request: Request, pk: str):
        container.delete_budget().execute(request.user.id, _uuid(pk))
        return no_content()
