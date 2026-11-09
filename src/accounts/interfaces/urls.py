"""URL routes for the accounts module (relative to /api/v1/)."""

from django.urls import path

from accounts.interfaces.views import (
    ChangePasswordView,
    ConfirmEmailView,
    ConfirmPasswordResetView,
    LoginView,
    LogoutView,
    PasswordChangeCodeView,
    ProfileDataView,
    ProfileView,
    RefreshTokenView,
    RegisterView,
    RequestPasswordResetView,
    ResendEmailCodeView,
    SocialLoginView,
)

app_name = "accounts"

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshTokenView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/password/reset/", RequestPasswordResetView.as_view(), name="password-reset"),
    path("auth/password/confirm/", ConfirmPasswordResetView.as_view(), name="password-confirm"),
    path("auth/social/<str:provider>/", SocialLoginView.as_view(), name="social"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/password/", ChangePasswordView.as_view(), name="change-password"),
    path("profile/password/code/", PasswordChangeCodeView.as_view(), name="change-password-code"),
    path("auth/email/confirm/", ConfirmEmailView.as_view(), name="email-confirm"),
    path("auth/email/resend/", ResendEmailCodeView.as_view(), name="email-resend"),
    path("profile/data/", ProfileDataView.as_view(), name="profile-data"),
]
