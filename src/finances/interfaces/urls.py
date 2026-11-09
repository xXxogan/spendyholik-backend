"""URL routes for the finances module (relative to /api/v1/)."""

from django.urls import path

from finances.interfaces.views import (
    AccountArchiveView,
    AccountBalanceHistoryView,
    AccountDetailView,
    AccountListCreateView,
    AccountUnarchiveView,
    BudgetDetailView,
    BudgetListCreateView,
    CategoryDetailView,
    CategoryListCreateView,
    FeedView,
    TransactionDetailView,
    TransactionListCreateView,
)

app_name = "finances"

urlpatterns = [
    path("accounts/", AccountListCreateView.as_view(), name="account-list"),
    path("accounts/<uuid:pk>/", AccountDetailView.as_view(), name="account-detail"),
    path("accounts/<uuid:pk>/archive/", AccountArchiveView.as_view(), name="account-archive"),
    path("accounts/<uuid:pk>/unarchive/", AccountUnarchiveView.as_view(), name="account-unarchive"),
    path(
        "accounts/<uuid:pk>/balance-history/",
        AccountBalanceHistoryView.as_view(),
        name="account-balance-history",
    ),
    path("transactions/", TransactionListCreateView.as_view(), name="transaction-list"),
    path("feed/", FeedView.as_view(), name="feed"),
    path("transactions/<uuid:pk>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("categories/", CategoryListCreateView.as_view(), name="category-list"),
    path("categories/<uuid:pk>/", CategoryDetailView.as_view(), name="category-detail"),
    path("budgets/", BudgetListCreateView.as_view(), name="budget-list"),
    path("budgets/<uuid:pk>/", BudgetDetailView.as_view(), name="budget-detail"),
]
