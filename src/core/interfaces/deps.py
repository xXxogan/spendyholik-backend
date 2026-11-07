"""Dependency container — wires use cases to their infrastructure implementations."""

from __future__ import annotations

from accounts.application.use_cases import (
    ChangePassword,
    ConfirmPasswordReset,
    GetProfile,
    LoginUser,
    LogoutUser,
    RefreshToken,
    RegisterUser,
    RequestPasswordReset,
    SocialLogin,
    UpdateProfile,
    WipeUserData,
)
from accounts.infrastructure.gateways import (
    DjangoCachePasswordResetGateway,
    DjangoPasswordHasher,
    SimpleJWTTokenService,
    SocialAuthIdentityProvider,
)
from accounts.infrastructure.repositories import DjangoProfileRepository, DjangoUserRepository
from analytics.application.use_cases import (
    GetDashboard,
    GetMonthlyTrend,
    GetSpendingByCategory,
    GetSummary,
    GetTrend,
)
from core.infrastructure.balances import DjangoBalanceReader
from core.infrastructure.erasure import DjangoUserDataEraser
from debts.application.use_cases import (
    CreateDebt,
    DeleteDebt,
    GetDebtDetail,
    GetDebtHistory,
    ListDebts,
    RepayDebt,
    UpdateDebt,
)
from debts.infrastructure.repositories import DjangoDebtPaymentRepository, DjangoDebtRepository
from finances.application.use_cases import (
    ArchiveAccount,
    BudgetReporter,
    CreateAccount,
    CreateBudget,
    CreateCategory,
    CreateTransaction,
    DeleteBudget,
    DeleteCategory,
    DeleteTransaction,
    GetAccountDetail,
    GetBalanceHistory,
    GetBudgetDetail,
    GetTransaction,
    ListAccounts,
    ListBudgets,
    ListCategories,
    ListTransactions,
    UnarchiveAccount,
    UpdateAccount,
    UpdateBudget,
    UpdateCategory,
    UpdateTransaction,
)
from finances.infrastructure.repositories import (
    DjangoAccountRepository,
    DjangoBudgetRepository,
    DjangoCategoryRepository,
    DjangoExchangeRateRepository,
    DjangoTransactionRepository,
)
from goals.application.use_cases import (
    ContributeToGoal,
    CreateGoal,
    DeleteGoal,
    ForecastGoal,
    GetGoalDetail,
    ListGoalContributions,
    ListGoals,
    UpdateGoal,
)
from goals.infrastructure.repositories import DjangoGoalContributionRepository, DjangoGoalRepository
from notifications.application.use_cases import ListNotifications, MarkNotificationsRead
from notifications.infrastructure.repositories import DjangoNotificationRepository
from recurring.application.use_cases import (
    CreateRecurring,
    DeleteRecurring,
    ListRecurring,
    RunDueRecurring,
    ToggleRecurring,
    UpdateRecurring,
)
from recurring.infrastructure.repositories import DjangoRecurringTransactionRepository
from shared.domain.clock import SystemClock
from shared.infrastructure.uow import DjangoUnitOfWork


class Container:
    """Lazily builds use cases; instantiate once per request if desired."""

    # --- accounts ---
    def register_user(self) -> RegisterUser:
        return RegisterUser(
            DjangoUserRepository(),
            DjangoProfileRepository(),
            DjangoPasswordHasher(),
            SimpleJWTTokenService(),
            DjangoUnitOfWork(),
        )

    def login_user(self) -> LoginUser:
        return LoginUser(DjangoUserRepository(), DjangoPasswordHasher(), SimpleJWTTokenService())

    def refresh_token(self) -> RefreshToken:
        return RefreshToken(SimpleJWTTokenService())

    def logout_user(self) -> LogoutUser:
        return LogoutUser(SimpleJWTTokenService())

    def social_login(self) -> SocialLogin:
        return SocialLogin(
            SocialAuthIdentityProvider(),
            DjangoUserRepository(),
            DjangoProfileRepository(),
            DjangoPasswordHasher(),
            SimpleJWTTokenService(),
            DjangoUnitOfWork(),
        )

    def request_password_reset(self) -> RequestPasswordReset:
        return RequestPasswordReset(DjangoUserRepository(), DjangoCachePasswordResetGateway())

    def confirm_password_reset(self) -> ConfirmPasswordReset:
        return ConfirmPasswordReset(
            DjangoUserRepository(),
            DjangoPasswordHasher(),
            DjangoCachePasswordResetGateway(),
            SimpleJWTTokenService(),
        )

    def get_profile(self) -> GetProfile:
        return GetProfile(DjangoProfileRepository(), DjangoUserRepository())

    def update_profile(self) -> UpdateProfile:
        return UpdateProfile(DjangoProfileRepository(), DjangoUserRepository(), DjangoUnitOfWork())

    def wipe_user_data(self) -> WipeUserData:
        return WipeUserData(DjangoUserDataEraser(), DjangoUnitOfWork())

    def change_password(self) -> ChangePassword:
        return ChangePassword(
            DjangoUserRepository(), DjangoPasswordHasher(), SimpleJWTTokenService()
        )

    # --- finances ---
    def create_account(self) -> CreateAccount:
        return CreateAccount(DjangoAccountRepository())

    def update_account(self) -> UpdateAccount:
        return UpdateAccount(DjangoAccountRepository(), DjangoBalanceReader())

    def archive_account(self) -> ArchiveAccount:
        return ArchiveAccount(DjangoAccountRepository(), DjangoBalanceReader())

    def unarchive_account(self) -> UnarchiveAccount:
        return UnarchiveAccount(DjangoAccountRepository(), DjangoBalanceReader())

    def list_accounts(self) -> ListAccounts:
        return ListAccounts(DjangoAccountRepository(), DjangoBalanceReader())

    def get_account_detail(self) -> GetAccountDetail:
        return GetAccountDetail(DjangoAccountRepository(), DjangoBalanceReader())

    def get_balance_history(self) -> GetBalanceHistory:
        return GetBalanceHistory(DjangoAccountRepository(), DjangoBalanceReader(), SystemClock())

    def list_categories(self) -> ListCategories:
        return ListCategories(DjangoCategoryRepository())

    def create_category(self) -> CreateCategory:
        return CreateCategory(DjangoCategoryRepository())

    def update_category(self) -> UpdateCategory:
        return UpdateCategory(DjangoCategoryRepository())

    def delete_category(self) -> DeleteCategory:
        return DeleteCategory(DjangoCategoryRepository())

    def create_transaction(self) -> CreateTransaction:
        return CreateTransaction(
            DjangoAccountRepository(), DjangoCategoryRepository(), DjangoTransactionRepository()
        )

    def update_transaction(self) -> UpdateTransaction:
        return UpdateTransaction(
            DjangoAccountRepository(), DjangoCategoryRepository(), DjangoTransactionRepository()
        )

    def delete_transaction(self) -> DeleteTransaction:
        return DeleteTransaction(DjangoTransactionRepository())

    def get_transaction(self) -> GetTransaction:
        return GetTransaction(DjangoTransactionRepository())

    def list_transactions(self) -> ListTransactions:
        return ListTransactions(DjangoTransactionRepository())

    def _budget_reporter(self) -> BudgetReporter:
        return BudgetReporter(
            DjangoTransactionRepository(),
            DjangoCategoryRepository(),
            DjangoExchangeRateRepository(),
            SystemClock(),
        )

    def create_budget(self) -> CreateBudget:
        return CreateBudget(
            DjangoBudgetRepository(),
            DjangoCategoryRepository(),
            DjangoProfileRepository(),
            self._budget_reporter(),
        )

    def update_budget(self) -> UpdateBudget:
        return UpdateBudget(
            DjangoBudgetRepository(), DjangoCategoryRepository(), self._budget_reporter()
        )

    def list_budgets(self) -> ListBudgets:
        return ListBudgets(DjangoBudgetRepository(), self._budget_reporter())

    def get_budget_detail(self) -> GetBudgetDetail:
        return GetBudgetDetail(DjangoBudgetRepository(), self._budget_reporter())

    def delete_budget(self) -> DeleteBudget:
        return DeleteBudget(DjangoBudgetRepository())

    # --- goals ---
    def create_goal(self) -> CreateGoal:
        return CreateGoal(
            DjangoGoalRepository(),
            DjangoGoalContributionRepository(),
            DjangoAccountRepository(),
            DjangoBalanceReader(),
            DjangoUnitOfWork(),
            SystemClock(),
        )

    def update_goal(self) -> UpdateGoal:
        return UpdateGoal(DjangoGoalRepository(), DjangoGoalContributionRepository())

    def list_goals(self) -> ListGoals:
        return ListGoals(DjangoGoalRepository(), DjangoGoalContributionRepository())

    def get_goal_detail(self) -> GetGoalDetail:
        return GetGoalDetail(DjangoGoalRepository(), DjangoGoalContributionRepository())

    def contribute_to_goal(self) -> ContributeToGoal:
        return ContributeToGoal(
            DjangoGoalRepository(),
            DjangoGoalContributionRepository(),
            DjangoAccountRepository(),
            DjangoBalanceReader(),
            DjangoUnitOfWork(),
        )

    def list_goal_contributions(self) -> ListGoalContributions:
        return ListGoalContributions(
            DjangoGoalRepository(), DjangoGoalContributionRepository(), DjangoAccountRepository()
        )

    def delete_goal(self) -> DeleteGoal:
        return DeleteGoal(DjangoGoalRepository())

    def forecast_goal(self) -> ForecastGoal:
        return ForecastGoal(
            DjangoGoalRepository(), DjangoGoalContributionRepository(), SystemClock()
        )

    # --- recurring ---
    def create_recurring(self) -> CreateRecurring:
        return CreateRecurring(
            DjangoRecurringTransactionRepository(),
            DjangoAccountRepository(),
            DjangoCategoryRepository(),
            SystemClock(),
        )

    def update_recurring(self) -> UpdateRecurring:
        return UpdateRecurring(
            DjangoRecurringTransactionRepository(),
            DjangoAccountRepository(),
            DjangoCategoryRepository(),
            SystemClock(),
        )

    def toggle_recurring(self) -> ToggleRecurring:
        return ToggleRecurring(
            DjangoRecurringTransactionRepository(),
            DjangoAccountRepository(),
            DjangoCategoryRepository(),
        )

    def delete_recurring(self) -> DeleteRecurring:
        return DeleteRecurring(DjangoRecurringTransactionRepository())

    def list_recurring(self) -> ListRecurring:
        return ListRecurring(
            DjangoRecurringTransactionRepository(),
            DjangoAccountRepository(),
            DjangoCategoryRepository(),
        )

    def run_due_recurring(self) -> RunDueRecurring:
        return RunDueRecurring(
            DjangoRecurringTransactionRepository(),
            DjangoTransactionRepository(),
            DjangoUnitOfWork(),
            SystemClock(),
        )

    # --- debts ---
    def create_debt(self) -> CreateDebt:
        return CreateDebt(DjangoDebtRepository(), SystemClock())

    def update_debt(self) -> UpdateDebt:
        return UpdateDebt(DjangoDebtRepository(), DjangoUnitOfWork())

    def list_debts(self) -> ListDebts:
        return ListDebts(DjangoDebtRepository())

    def delete_debt(self) -> DeleteDebt:
        return DeleteDebt(DjangoDebtRepository())

    def get_debt_detail(self) -> GetDebtDetail:
        return GetDebtDetail(DjangoDebtRepository(), DjangoDebtPaymentRepository())

    def get_debt_history(self) -> GetDebtHistory:
        return GetDebtHistory(
            DjangoDebtRepository(), DjangoDebtPaymentRepository(), DjangoAccountRepository()
        )

    def repay_debt(self) -> RepayDebt:
        return RepayDebt(
            DjangoDebtRepository(),
            DjangoDebtPaymentRepository(),
            DjangoAccountRepository(),
            DjangoBalanceReader(),
            DjangoUnitOfWork(),
        )

    # --- analytics ---
    def get_dashboard(self) -> GetDashboard:
        return GetDashboard(
            DjangoAccountRepository(),
            DjangoTransactionRepository(),
            DjangoBudgetRepository(),
            DjangoProfileRepository(),
            DjangoExchangeRateRepository(),
            SystemClock(),
            DjangoBalanceReader(),
            DjangoCategoryRepository(),
        )

    def get_summary(self) -> GetSummary:
        return GetSummary(
            DjangoTransactionRepository(), DjangoProfileRepository(), DjangoExchangeRateRepository()
        )

    def get_spending_by_category(self) -> GetSpendingByCategory:
        return GetSpendingByCategory(
            DjangoTransactionRepository(),
            DjangoCategoryRepository(),
            DjangoProfileRepository(),
            DjangoExchangeRateRepository(),
        )

    def get_monthly_trend(self) -> GetMonthlyTrend:
        return GetMonthlyTrend(
            DjangoTransactionRepository(),
            DjangoProfileRepository(),
            DjangoExchangeRateRepository(),
            SystemClock(),
        )

    def get_trend(self) -> GetTrend:
        return GetTrend(
            DjangoTransactionRepository(),
            DjangoProfileRepository(),
            DjangoExchangeRateRepository(),
            SystemClock(),
        )

    # --- notifications ---
    def list_notifications(self) -> ListNotifications:
        return ListNotifications(DjangoNotificationRepository())

    def mark_notifications_read(self) -> MarkNotificationsRead:
        return MarkNotificationsRead(DjangoNotificationRepository())


container = Container()
