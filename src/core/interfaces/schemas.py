"""OpenAPI documentation of the API responses and query parameters.

The pydantic models here only *describe* what ``core.interfaces.renderers``
produces, so drf-spectacular can publish response schemas; they are never
used to build responses. Keep them in step with the renderers
(``tests/api/test_openapi_schema.py`` checks the main shapes).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from drf_spectacular.contrib.pydantic import PydanticExtension
from drf_spectacular.plumbing import ResolvedComponent
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from pydantic import BaseModel, Field, RootModel
from pydantic.json_schema import GenerateJsonSchema, model_json_schema

from accounts.domain.enums import Theme
from debts.domain.enums import DebtDirection, DebtEventKind
from finances.domain.enums import AccountType, BudgetPeriod, TransactionType
from notifications.domain.enums import NotificationType
from recurring.domain.enums import RecurringFrequency


# ---------------------------------------------------------------------------
# pydantic → OpenAPI 3.0
# ---------------------------------------------------------------------------
class _OpenApi30JsonSchema(GenerateJsonSchema):
    """JSON Schema dialect of OpenAPI 3.0: ``nullable`` instead of ``type: null``,
    ``enum`` instead of ``const``."""

    def nullable_schema(self, schema):
        inner = self.generate_inner(schema["schema"])
        if "$ref" in inner:
            return {"allOf": [inner], "nullable": True}
        return {**inner, "nullable": True}

    def literal_schema(self, schema):
        result = super().literal_schema(schema)
        if "const" in result:
            result["enum"] = [result.pop("const")]
        return result


def _openapi30_bounds(node):
    """JSON Schema's numeric ``exclusiveMinimum: 0`` → OpenAPI 3.0's
    ``minimum: 0, exclusiveMinimum: true`` (same for the maximum), recursively."""
    if isinstance(node, dict):
        for key, bound in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
            value = node.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                node[bound] = value
                node[key] = True
        for value in node.values():
            _openapi30_bounds(value)
    elif isinstance(node, list):
        for value in node:
            _openapi30_bounds(value)
    return node


class OpenApi30PydanticExtension(PydanticExtension):
    """Describes pydantic models (requests and responses) as valid OpenAPI 3.0."""

    priority = 1

    def map_serializer(self, auto_schema, direction):
        schema = model_json_schema(
            self.target,
            ref_template="#/components/schemas/{model}",
            mode="serialization",
            schema_generator=_OpenApi30JsonSchema,
        )
        _openapi30_bounds(schema)
        for sub_name, sub_schema in schema.pop("$defs", {}).items():
            component = ResolvedComponent(
                name=sub_name, type=ResolvedComponent.SCHEMA, object=sub_name, schema=sub_schema
            )
            auto_schema.registry.register_on_missing(component)
        return schema


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
class MoneyOut(BaseModel):
    minor: int = Field(description="Amount in minor units (kopecks, cents).")
    currency: str = Field(description="ISO 4217 code.")
    formatted: str = Field(description='Display string, e.g. "1 240 ₽".')


class AccountRefOut(BaseModel):
    id: str
    name: str | None
    color: str | None


class CategoryRefOut(BaseModel):
    id: str
    name: str | None
    icon: str | None
    color: str | None


class ErrorOut(BaseModel):
    code: str = Field(description='Machine-readable error, e.g. "validation_error".')
    detail: str = Field(description="Human-readable message (English, may change).")
    errors: dict[str, str] = Field(
        description='Field → code, e.g. {"amount_minor": "required"}. Codes: required, '
        "invalid, invalid_choice, too_short, too_long, too_small, too_large, "
        "currency_mismatch and domain codes (wrong_password, budget_already_exists, "
        "insufficient_funds, exceeds_target, below_repaid, email_already_taken, "
        "invalid_code, code_expired, too_many_attempts, …)."
    )


class DetailOut(BaseModel):
    detail: str


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, bool]


# ---------------------------------------------------------------------------
# Auth and profile
# ---------------------------------------------------------------------------
class UserOut(BaseModel):
    id: str
    email: str
    first_name: str
    email_verified: bool = Field(description="False until the mailed code is entered.")


class TokensOut(BaseModel):
    access: str
    refresh: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class AuthOut(TokensOut):
    user: UserOut


class ProfileOut(BaseModel):
    user_id: str
    first_name: str
    email: str
    email_verified: bool
    personal_data_consent_at: datetime | None = Field(
        description="When consent to personal data processing was given at registration."
    )
    base_currency: str
    theme: Theme
    onboarded: bool
    notify_budget: bool
    notify_goal: bool
    notify_recurring: bool
    notify_income: bool
    notify_weekly_report: bool


class PasswordResetOut(BaseModel):
    acknowledged: bool


# ---------------------------------------------------------------------------
# Finances
# ---------------------------------------------------------------------------
class AccountOut(BaseModel):
    id: str
    name: str
    type: AccountType
    currency: str
    balance: MoneyOut = Field(
        description="Current balance: initial ± transactions, goal contributions, repayments."
    )
    initial_balance: MoneyOut
    color: str
    last4: str | None
    credit_limit: MoneyOut | None
    interest_rate: str
    is_archived: bool


class BalancePointOut(BaseModel):
    at: date
    balance: MoneyOut


class CategoryOut(BaseModel):
    id: str
    name: str
    type: TransactionType
    icon: str
    color: str
    parent_id: str | None
    is_system: bool
    transaction_count: int = Field(description="Transactions in this category itself.")


class TransactionOut(BaseModel):
    id: str
    type: TransactionType
    amount: MoneyOut
    title: str = Field(description="Given name, or the category (account for a transfer) name.")
    subtitle: str
    category: CategoryRefOut | None
    account: AccountRefOut
    transfer_to_account: AccountRefOut | None = Field(description="Destination of a transfer.")
    date: date
    time: str | None
    note: str
    receipt: dict[str, str] | None


class TransactionPageOut(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None


class FeedDebtOut(BaseModel):
    id: str
    person_name: str
    direction: DebtDirection


class FeedGoalOut(BaseModel):
    id: str
    name: str


class FeedItemOut(BaseModel):
    kind: Literal["transaction", "debt_opening", "debt_payment", "goal_contribution"]
    id: str = Field(description="Id of the transaction, debt (opening), payment or contribution.")
    date: date
    amount: MoneyOut
    effect: Literal["in", "out", "transfer"] = Field(
        description="How it moves the account; `transfer` only without an account filter."
    )
    account: AccountRefOut | None
    transaction: TransactionOut | None = Field(description="Set for `kind = transaction`.")
    debt: FeedDebtOut | None = Field(description="Set for debt openings and repayments.")
    goal: FeedGoalOut | None = Field(description="Set for goal contributions.")


class FeedPageOut(BaseModel):
    items: list[FeedItemOut]
    next_cursor: str | None


class BudgetOut(BaseModel):
    id: str
    category: CategoryRefOut
    category_id: str
    amount: MoneyOut
    spent: MoneyOut = Field(description="Expenses of the category and its subcategories.")
    period: BudgetPeriod
    start_date: date | None
    end_date: date | None
    period_start: date | None = Field(description="First day of the current period.")
    period_end: date | None = Field(description="Last day of the current period (inclusive).")
    is_active: bool


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------
class GoalOut(BaseModel):
    id: str
    name: str
    target_amount: MoneyOut
    current_amount: MoneyOut
    account_id: str | None
    deadline: date | None
    icon: str
    color: str
    progress: float


class ContributionOut(BaseModel):
    id: str
    goal_id: str
    account_id: str | None
    account: AccountRefOut | None
    amount: MoneyOut
    date: date


class ForecastOut(BaseModel):
    goal_id: str
    remaining: MoneyOut
    projected_completion: date | None


# ---------------------------------------------------------------------------
# Debts
# ---------------------------------------------------------------------------
class DebtOut(BaseModel):
    id: str
    person_name: str
    direction: DebtDirection
    amount: MoneyOut
    remaining: MoneyOut
    due_date: date | None
    is_closed: bool
    note: str
    created_at: datetime | None
    account_id: str | None = Field(description="Account the opening moved money through.")
    opened_on: date | None


class DebtPaymentOut(BaseModel):
    id: str
    debt_id: str
    account_id: str | None
    amount: MoneyOut
    date: date


class DebtEventOut(BaseModel):
    id: str
    kind: DebtEventKind
    amount: MoneyOut
    date: date
    account: AccountRefOut | None = Field(description="Null for the opening.")


# ---------------------------------------------------------------------------
# Recurring
# ---------------------------------------------------------------------------
class RecurringOut(BaseModel):
    id: str
    name: str
    amount: MoneyOut
    type: Literal["expense", "income"]
    account_id: str
    category_id: str | None
    account: AccountRefOut | None
    category: CategoryRefOut | None
    frequency: RecurringFrequency
    anchor_date: date | None = Field(description="First occurrence; the schedule counts from it.")
    next_run: date
    is_active: bool


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class BudgetStatusOut(BaseModel):
    budget_id: str
    category_id: str
    limit: MoneyOut
    spent: MoneyOut
    remaining: MoneyOut
    ratio: float


class DashboardOut(BaseModel):
    total_balance: MoneyOut
    income_this_month: MoneyOut
    expense_this_month: MoneyOut
    net_this_month: MoneyOut
    budgets: list[BudgetStatusOut]
    excluded_currencies: list[str]


class SummaryOut(BaseModel):
    income: MoneyOut
    expense: MoneyOut
    net: MoneyOut
    excluded_currencies: list[str]


class CategorySpendingOut(BaseModel):
    category: CategoryRefOut | None = Field(description="Top-level category.")
    category_id: str
    category_name: str
    amount: MoneyOut
    ratio: float


class MonthlyPointOut(BaseModel):
    month: date
    income: MoneyOut
    expense: MoneyOut


class TrendPointOut(BaseModel):
    start: date = Field(description="First day of the day/month/year bucket.")
    income: MoneyOut
    expense: MoneyOut


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    subject: str = Field(description="What it is about: category, payer, template or goal name.")
    amount_minor: int | None
    currency: str | None = Field(description="Currency of `amount_minor`.")
    percent: int | None = Field(
        description="Budget: share spent (may exceed 100); goal: threshold reached (50/75/100)."
    )
    title: str
    body: str
    is_read: bool
    created_at: datetime | None


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------
def _query(name: str, type_, description: str, **kwargs) -> OpenApiParameter:
    return OpenApiParameter(
        name, type_, OpenApiParameter.QUERY, required=False, description=description, **kwargs
    )


DATE_RANGE = [
    _query("date_from", OpenApiTypes.DATE, "First day, inclusive."),
    _query("date_to", OpenApiTypes.DATE, "Last day, inclusive."),
]
TRANSACTION_FILTERS = [
    _query(
        "account_id", OpenApiTypes.UUID, "This account as the source or a transfer's destination."
    ),
    _query("category_id", OpenApiTypes.UUID, "This category and all its subcategories."),
    _query("type", OpenApiTypes.STR, "Transaction type.", enum=["expense", "income", "transfer"]),
    *DATE_RANGE,
    _query("search", OpenApiTypes.STR, "Substring of the title or the note."),
    _query("cursor", OpenApiTypes.STR, "`next_cursor` of the previous page."),
    _query("limit", OpenApiTypes.INT, "Page size, 1–100 (default 20)."),
]
FEED_FILTERS = [
    _query("account_id", OpenApiTypes.UUID, "Movements of this account only."),
    *DATE_RANGE,
    _query("cursor", OpenApiTypes.STR, "`next_cursor` of the previous page."),
    _query("limit", OpenApiTypes.INT, "Page size, 1–100 (default 20)."),
]
INCLUDE_ARCHIVED = [_query("include_archived", OpenApiTypes.BOOL, "Also list archived accounts.")]
WEEKS = [_query("weeks", OpenApiTypes.INT, "How many weeks back, 1–104 (default 6).")]
MONTHS = [_query("months", OpenApiTypes.INT, "How many months, 1–36 (default 6).")]
TREND = [
    _query(
        "granularity",
        OpenApiTypes.STR,
        "Bucket size (default month). Without dates: 7 days, 6 months or 3 years.",
        enum=["day", "month", "year"],
    ),
    *DATE_RANGE,
]


def many(model: type[BaseModel]) -> type[BaseModel]:
    """A JSON array of ``model``, as a named schema component (``AccountOutList``)."""
    return type(f"{model.__name__}List", (RootModel[list[model]],), {"__module__": __name__})


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------
_ERRORS = {
    401: "Not authenticated.",
    403: "The email is not confirmed yet (`email_not_verified`).",
    404: "Not found.",
    409: "A business rule prevented the operation.",
    422: "Validation failed; see `errors`.",
    429: "Too many attempts or requests (`too_many_attempts`, `too_many_codes`, "
    "`resend_too_soon`, `throttled`).",
}


def api_doc(
    response=None,
    *,
    request=None,
    status: int = 200,
    parameters=None,
    errors=(401, 403),
    description: str | None = None,
    operation_id: str | None = None,
):
    """``extend_schema`` with the success body and the unified error responses."""
    responses = {status: response}
    for code in errors:
        responses[code] = OpenApiResponse(ErrorOut, description=_ERRORS[code])
    return extend_schema(
        request=request,
        responses=responses,
        parameters=parameters,
        description=description,
        operation_id=operation_id,
    )


READ = (401, 403, 404)
WRITE = (401, 403, 404, 409, 422)
