"""One-time codes mailed to confirm an email or a password change.

Six digits, alive for :data:`CODE_TTL`, at most :data:`MAX_ATTEMPTS` wrong
entries, a new one no sooner than :data:`RESEND_COOLDOWN` after the last.
Only an HMAC of the code is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from accounts.application.ports import CodeSender, VerificationCodeRepository
from accounts.domain.entities import User, VerificationCode
from accounts.domain.enums import CodePurpose
from accounts.domain.exceptions import (
    CodeExpiredError,
    InvalidCodeError,
    ResendTooSoonError,
    TooManyAttemptsError,
    TooManyCodesError,
)
from shared.domain.clock import Clock

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
#: Codes per user and purpose per day (UTC), so a mailbox cannot be flooded.
MAX_CODES_PER_DAY = 10


class VerificationCodes:
    def __init__(
        self,
        codes: VerificationCodeRepository,
        sender: CodeSender,
        clock: Clock,
        pepper: str,
    ) -> None:
        self._codes = codes
        self._sender = sender
        self._clock = clock
        self._pepper = pepper.encode()

    def _hash(self, code: str) -> str:
        return hmac.new(self._pepper, code.encode(), hashlib.sha256).hexdigest()

    def issue(self, user: User, purpose: CodePurpose) -> None:
        """Mail a fresh code; the previous one of the same purpose stops working."""
        now = self._clock.now()
        current = self._codes.get_live(user.id, purpose)
        sent_count = 1
        if current is not None:
            wait = current.sent_at + RESEND_COOLDOWN - now
            if wait.total_seconds() > 0:
                raise ResendTooSoonError(int(wait.total_seconds()) + 1)
            if current.sent_at.date() == now.date():
                sent_count = current.sent_count + 1
        if sent_count > MAX_CODES_PER_DAY:
            raise TooManyCodesError
        code = f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"
        self._codes.replace(
            VerificationCode(
                user_id=user.id,
                purpose=purpose,
                code_hash=self._hash(code),
                sent_at=now,
                expires_at=now + CODE_TTL,
                sent_count=sent_count,
            )
        )
        self._sender.send(user, purpose, code, int(CODE_TTL.total_seconds() // 60))

    def revoke(self, user_id, purpose: CodePurpose) -> None:
        """Forget the live code of this purpose (e.g. one mailed to an old address)."""
        self._codes.delete_for(user_id, purpose)

    def verify(self, user_id, purpose: CodePurpose, code: str) -> None:
        """Accept and burn a correct code.

        Call it *outside* the unit of work that applies the change: a wrong
        attempt must stay counted although the error aborts the request. The
        attempt is reserved atomically before comparing, so parallel guesses
        cannot exceed :data:`MAX_ATTEMPTS`.
        """
        current = self._codes.get_live(user_id, purpose)
        if current is None:
            raise InvalidCodeError
        if self._clock.now() >= current.expires_at:
            raise CodeExpiredError
        if not self._codes.reserve_attempt(current.id, MAX_ATTEMPTS):
            raise TooManyAttemptsError
        if not hmac.compare_digest(current.code_hash, self._hash(code.strip())):
            if current.attempts + 1 >= MAX_ATTEMPTS:
                raise TooManyAttemptsError
            raise InvalidCodeError
        self._codes.delete(current.id)
