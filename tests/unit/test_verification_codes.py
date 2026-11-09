"""B-22: one-time codes — expiry, attempts, resend cooldown."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from accounts.application.codes import MAX_ATTEMPTS, RESEND_COOLDOWN
from accounts.domain.entities import User
from accounts.domain.enums import CodePurpose
from accounts.domain.exceptions import (
    CodeExpiredError,
    InvalidCodeError,
    ResendTooSoonError,
    TooManyAttemptsError,
)
from accounts.domain.value_objects import Email
from tests.fakes import fake_codes

PURPOSE = CodePurpose.VERIFY_EMAIL


class MovableClock:
    def __init__(self) -> None:
        self.at = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    def now(self):
        return self.at


@pytest.fixture
def world():
    clock = MovableClock()
    codes, sender, repo = fake_codes(clock)
    user = User(email=Email("a@b.co"), id=uuid4())
    codes.issue(user, PURPOSE)
    return clock, codes, sender, repo, user


def test_code_is_six_digits_and_only_its_hash_is_kept(world):
    _, _, sender, repo, user = world
    code = sender.last_code
    assert len(code) == 6 and code.isdigit()
    assert code not in repo.get_live(user.id, PURPOSE).code_hash


def test_right_code_passes_once(world):
    _, codes, sender, _, user = world
    codes.verify(user.id, PURPOSE, f" {sender.last_code} ")
    with pytest.raises(InvalidCodeError):
        codes.verify(user.id, PURPOSE, sender.last_code)


def test_expired_code(world):
    clock, codes, sender, _, user = world
    clock.at += timedelta(minutes=16)
    with pytest.raises(CodeExpiredError):
        codes.verify(user.id, PURPOSE, sender.last_code)


def test_attempts_are_limited(world):
    _, codes, sender, _, user = world
    for _ in range(MAX_ATTEMPTS - 1):
        with pytest.raises(InvalidCodeError):
            codes.verify(user.id, PURPOSE, "nope")
    with pytest.raises(TooManyAttemptsError):
        codes.verify(user.id, PURPOSE, "nope")
    with pytest.raises(TooManyAttemptsError):  # even the right one now
        codes.verify(user.id, PURPOSE, sender.last_code)


def test_resend_cooldown_and_new_code_replaces_old(world):
    clock, codes, sender, _, user = world
    old = sender.last_code
    with pytest.raises(ResendTooSoonError) as exc:
        codes.issue(user, PURPOSE)
    assert exc.value.retry_after > 0
    clock.at += RESEND_COOLDOWN
    codes.issue(user, PURPOSE)
    if sender.last_code != old:
        with pytest.raises(InvalidCodeError):
            codes.verify(user.id, PURPOSE, old)
    codes.verify(user.id, PURPOSE, sender.last_code)


def test_purposes_are_separate(world):
    _, codes, sender, _, user = world
    with pytest.raises(InvalidCodeError):
        codes.verify(user.id, CodePurpose.CHANGE_PASSWORD, sender.last_code)


def test_daily_cap(world):
    clock, codes, _, repo, user = world
    from accounts.application.codes import MAX_CODES_PER_DAY
    from accounts.domain.exceptions import TooManyCodesError

    for _ in range(MAX_CODES_PER_DAY - 1):
        clock.at += RESEND_COOLDOWN
        codes.issue(user, PURPOSE)
    clock.at += RESEND_COOLDOWN
    with pytest.raises(TooManyCodesError):
        codes.issue(user, PURPOSE)
    clock.at += timedelta(days=1)
    codes.issue(user, PURPOSE)  # a new day
    assert repo.get_live(user.id, PURPOSE).sent_count == 1


def test_revoke(world):
    _, codes, sender, _, user = world
    codes.revoke(user.id, PURPOSE)
    with pytest.raises(InvalidCodeError):
        codes.verify(user.id, PURPOSE, sender.last_code)
