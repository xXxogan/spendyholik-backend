from datetime import datetime, timezone

from shared.domain.clock import Clock, SystemClock


class TestClock:
    def test_system_clock_returns_aware_utc(self):
        clock: Clock = SystemClock()
        now = clock.now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None
        assert now.utcoffset() == timezone.utc.utcoffset(now)
