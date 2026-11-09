"""DRF views for the accounts bounded context (auth + profile)."""

from __future__ import annotations

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.throttling import ScopedRateThrottle

from accounts.application.dto import (
    ChangePasswordInput,
    ConfirmEmailInput,
    ConfirmPasswordResetInput,
    LoginUserInput,
    RefreshTokenInput,
    RegisterUserInput,
    RequestPasswordResetInput,
    SocialLoginInput,
    UpdateProfileInput,
)
from core.interfaces import schemas as sc
from core.interfaces.api import BaseAPIView, created, no_content, ok
from core.interfaces.deps import container
from core.interfaces.permissions import IsVerified
from core.interfaces.schemas import api_doc


def _user_view(user) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "email_verified": user.email_verified,
    }


def _auth_view(result) -> dict:
    return {
        "user": _user_view(result.user),
        "access": result.tokens.access,
        "refresh": result.tokens.refresh,
        "access_expires_at": result.tokens.access_expires_at.isoformat(),
        "refresh_expires_at": result.tokens.refresh_expires_at.isoformat(),
    }


def _profile_view(dto) -> dict:
    return {
        "user_id": str(dto.user_id),
        "first_name": dto.first_name,
        "email": dto.email,
        "email_verified": dto.email_verified,
        "personal_data_consent_at": dto.personal_data_consent_at.isoformat()
        if dto.personal_data_consent_at
        else None,
        "base_currency": dto.base_currency,
        "theme": dto.theme.value,
        "onboarded": dto.onboarded,
        "notify_budget": dto.notify_budget,
        "notify_goal": dto.notify_goal,
        "notify_recurring": dto.notify_recurring,
        "notify_income": dto.notify_income,
        "notify_weekly_report": dto.notify_weekly_report,
    }


class RegisterView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.AuthOut, request=RegisterUserInput, status=201, errors=(409, 422))
    def post(self, request: Request):
        data = self.parse(RegisterUserInput, request.data)
        return created(_auth_view(container.register_user().execute(data)))


class LoginView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.AuthOut, request=LoginUserInput, errors=(401, 422))
    def post(self, request: Request):
        data = self.parse(LoginUserInput, request.data)
        return ok(_auth_view(container.login_user().execute(data)))


class RefreshTokenView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.TokensOut, request=RefreshTokenInput, errors=(401, 422))
    def post(self, request: Request):
        data = self.parse(RefreshTokenInput, request.data)
        pair = container.refresh_token().execute(data)
        return ok(
            {
                "access": pair.access,
                "refresh": pair.refresh,
                "access_expires_at": pair.access_expires_at.isoformat(),
                "refresh_expires_at": pair.refresh_expires_at.isoformat(),
            }
        )


class LogoutView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.DetailOut, request=RefreshTokenInput, errors=(401, 422))
    def post(self, request: Request):
        data = self.parse(RefreshTokenInput, request.data)
        container.logout_user().execute(data)
        return ok({"detail": "ok"})


class RequestPasswordResetView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.PasswordResetOut, request=RequestPasswordResetInput, errors=(422,))
    def post(self, request: Request):
        data = self.parse(RequestPasswordResetInput, request.data)
        result = container.request_password_reset().execute(data)
        return ok({"acknowledged": result.acknowledged})


class ConfirmPasswordResetView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.DetailOut, request=ConfirmPasswordResetInput, errors=(422,))
    def post(self, request: Request):
        data = self.parse(ConfirmPasswordResetInput, request.data)
        container.confirm_password_reset().execute(data)
        return ok({"detail": "ok"})


class SocialLoginView(BaseAPIView):
    permission_classes = [AllowAny]

    @api_doc(sc.AuthOut, request=SocialLoginInput, errors=(401, 422))
    def post(self, request: Request, provider: str):
        data = self.parse(
            SocialLoginInput,
            {"provider": provider, "credential": request.data.get("credential", "")},
        )
        return ok(_auth_view(container.social_login().execute(data)))


class ProfileView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    @api_doc(sc.ProfileOut, errors=sc.READ)
    def get(self, request: Request):
        return ok(_profile_view(container.get_profile().execute(request.user.id)))

    @api_doc(
        sc.ProfileOut,
        request=UpdateProfileInput,
        errors=(*sc.WRITE, 429),
        description="A new `email` needs `current_password`, is unconfirmed until its code "
        "is entered, and the old address is told about the change.",
    )
    def patch(self, request: Request):
        data = self.parse(UpdateProfileInput, request.data)
        return ok(_profile_view(container.update_profile().execute(request.user.id, data)))


class ProfileDataView(BaseAPIView):
    permission_classes = [IsVerified]

    @api_doc(
        None,
        status=204,
        description=(
            "Deletes all accounts, transactions, categories, budgets, goals, debts, "
            "recurring templates and notifications; the user and settings stay."
        ),
    )
    def delete(self, request: Request):
        container.wipe_user_data().execute(request.user.id)
        return no_content()


class ChangePasswordView(BaseAPIView):
    permission_classes = [IsVerified]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "codes"

    @api_doc(
        sc.DetailOut,
        request=ChangePasswordInput,
        errors=(401, 403, 422, 429),
        description="Needs the code from `POST profile/password/code/`; revokes every session.",
    )
    def patch(self, request: Request):
        data = self.parse(ChangePasswordInput, request.data)
        container.change_password().execute(request.user.id, data)
        return ok({"detail": "ok"})


class PasswordChangeCodeView(BaseAPIView):
    permission_classes = [IsVerified]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "codes"

    @api_doc(
        sc.DetailOut,
        request=None,
        errors=(401, 403, 429),
        description="Mails a code that confirms the next password change.",
    )
    def post(self, request: Request):
        container.request_password_change_code().execute(request.user.id)
        return ok({"detail": "ok"})


class ConfirmEmailView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "codes"

    @api_doc(sc.UserOut, request=ConfirmEmailInput, errors=(401, 409, 422, 429))
    def post(self, request: Request):
        data = self.parse(ConfirmEmailInput, request.data)
        return ok(_user_view(container.confirm_email().execute(request.user.id, data)))


class ResendEmailCodeView(BaseAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "codes"

    @api_doc(
        sc.DetailOut,
        request=None,
        errors=(401, 409, 429),
        description="Mails a new confirmation code; at most once a minute.",
    )
    def post(self, request: Request):
        container.resend_email_code().execute(request.user.id)
        return ok({"detail": "ok"})
