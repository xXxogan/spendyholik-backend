"""DRF views for the accounts bounded context (auth + profile)."""

from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request

from accounts.application.dto import (
    ChangePasswordInput,
    ConfirmPasswordResetInput,
    LoginUserInput,
    RegisterUserInput,
    RequestPasswordResetInput,
    RefreshTokenInput,
    SocialLoginInput,
    UpdateProfileInput,
)
from accounts.application.use_cases import LogoutUser, RefreshToken
from core.interfaces.api import BaseAPIView, created, ok
from core.interfaces.deps import container
from core.interfaces.renderers import CURRENCY_SYMBOLS


def _auth_view(result) -> dict:
    return {
        "user": {
            "id": str(result.user.id),
            "email": result.user.email,
            "first_name": result.user.first_name,
        },
        "access": result.tokens.access,
        "refresh": result.tokens.refresh,
        "access_expires_at": result.tokens.access_expires_at.isoformat(),
        "refresh_expires_at": result.tokens.refresh_expires_at.isoformat(),
    }


def _profile_view(dto) -> dict:
    return {
        "user_id": str(dto.user_id),
        "base_currency": dto.base_currency,
        "theme": dto.theme.value,
        "onboarded": dto.onboarded,
        "notify_budget": dto.notify_budget,
        "notify_goal": dto.notify_goal,
        "notify_recurring": dto.notify_recurring,
        "notify_weekly_report": dto.notify_weekly_report,
    }


class RegisterView(BaseAPIView):
    permission_classes = [AllowAny]

    def post(self, request: Request):
        data = self.parse(RegisterUserInput, request.data)
        return created(_auth_view(container.register_user().execute(data)))


class LoginView(BaseAPIView):
    permission_classes = [AllowAny]

    def post(self, request: Request):
        data = self.parse(LoginUserInput, request.data)
        return ok(_auth_view(container.login_user().execute(data)))


class RefreshTokenView(BaseAPIView):
    permission_classes = [AllowAny]

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

    def post(self, request: Request):
        data = self.parse(RefreshTokenInput, request.data)
        container.logout_user().execute(data)
        return ok({"detail": "ok"})


class RequestPasswordResetView(BaseAPIView):
    permission_classes = [AllowAny]

    def post(self, request: Request):
        data = self.parse(RequestPasswordResetInput, request.data)
        result = container.request_password_reset().execute(data)
        return ok({"acknowledged": result.acknowledged})


class ConfirmPasswordResetView(BaseAPIView):
    permission_classes = [AllowAny]

    def post(self, request: Request):
        data = self.parse(ConfirmPasswordResetInput, request.data)
        container.confirm_password_reset().execute(data)
        return ok({"detail": "ok"})


class SocialLoginView(BaseAPIView):
    permission_classes = [AllowAny]

    def post(self, request: Request, provider: str):
        data = self.parse(SocialLoginInput, {"provider": provider, "credential": request.data.get("credential", "")})
        return ok(_auth_view(container.social_login().execute(data)))


class ProfileView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return ok(_profile_view(container.get_profile().execute(request.user.id)))

    def patch(self, request: Request):
        data = self.parse(UpdateProfileInput, request.data)
        return ok(_profile_view(container.update_profile().execute(request.user.id, data)))


class ChangePasswordView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request):
        data = self.parse(ChangePasswordInput, request.data)
        container.change_password().execute(request.user.id, data)
        return ok({"detail": "ok"})
