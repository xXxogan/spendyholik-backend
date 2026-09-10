"""DRF views for the debts bounded context."""

from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from core.interfaces.api import BaseAPIView, created, ok
from core.interfaces.deps import container
from core.interfaces.renderers import debt_to_view, money_to_view
from debts.application.dto import CreateDebtInput, RepayDebtInput, UpdateDebtInput


def _uuid(value):
    return value if isinstance(value, UUID) else UUID(value)


class DebtListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok([debt_to_view(d) for d in container.list_debts().execute(request.user.id)])

    def post(self, request: Request):
        data = self.parse(CreateDebtInput, request.data)
        return created(debt_to_view(container.create_debt().execute(request.user.id, data)))


class DebtDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk):
        return ok(debt_to_view(container.get_debt_detail().execute(request.user.id, _uuid(pk))))

    def patch(self, request: Request, pk):
        data = self.parse(UpdateDebtInput, request.data)
        return ok(debt_to_view(container.update_debt().execute(request.user.id, _uuid(pk), data)))


class DebtRepayView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk):
        data = self.parse(RepayDebtInput, request.data)
        payment = container.repay_debt().execute(request.user.id, _uuid(pk), data)
        return created(
            {
                "id": str(payment.id),
                "debt_id": str(payment.debt_id),
                "account_id": str(payment.account_id),
                "amount": money_to_view(payment.amount),
                "date": payment.date.isoformat(),
            }
        )
