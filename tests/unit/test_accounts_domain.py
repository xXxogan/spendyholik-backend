from uuid import uuid4

import pytest

from accounts.domain.entities import Profile, User
from accounts.domain.enums import Theme
from accounts.domain.value_objects import Email
from shared.exceptions import ValidationError


class TestEmail:
    def test_normalizes_to_lowercase(self):
        assert Email("User@Example.COM").value == "user@example.com"

    def test_rejects_invalid(self):
        with pytest.raises(ValidationError):
            Email("not-an-email")


class TestUser:
    def test_creates_user(self):
        user = User(email=Email("a@b.co"), first_name="Ann")
        assert str(user.email) == "a@b.co"
        assert user.first_name == "Ann"
        assert user.id is not None


class TestProfile:
    def test_defaults(self):
        profile = Profile(user_id=uuid4())
        assert profile.base_currency.value == "RUB"
        assert profile.theme is Theme.AUTO
        assert profile.onboarded is False

    def test_custom_values(self):
        profile = Profile(user_id=uuid4(), theme=Theme.DARK, onboarded=True)
        assert profile.theme is Theme.DARK
        assert profile.onboarded is True


class TestTheme:
    def test_values(self):
        assert {t.value for t in Theme} == {"light", "dark", "auto"}
