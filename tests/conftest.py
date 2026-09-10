"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.infrastructure.orm.models import Profile
from tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    u = UserFactory(password="password123")
    Profile.objects.get_or_create(user=u)
    return u


@pytest.fixture
def auth_client(db, user) -> APIClient:
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client
