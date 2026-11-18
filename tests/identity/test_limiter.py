"""Account lock is five failures. The IP window is twenty attempts."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.identity.adapters.memory import MemoryAttempts
from backend.identity.adapters.memory_rate_limiter import WindowLimiter


class WindowLimiterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
        self.limiter = WindowLimiter(MemoryAttempts())

    def test_five_failures_lock_the_account_on_the_next_check(self) -> None:
        for _ in range(4):
            self.limiter.hit("user", "ip-a", self.now, "fail", "invalid_credentials")
        self.assertIsNone(self.limiter.check("user", "ip-b", self.now))
        self.limiter.hit("user", "ip-a", self.now, "fail", "invalid_credentials")
        self.assertEqual(self.limiter.check("user", "ip-b", self.now), "account_locked")

    def test_twenty_attempts_throttle_the_ip(self) -> None:
        for index in range(20):
            self.limiter.hit(f"user-{index}", "ip-same", self.now, "fail", "invalid_credentials")
        self.assertEqual(self.limiter.check("user-new", "ip-same", self.now), "ip_throttled")

    def test_old_failures_leave_the_window(self) -> None:
        self.limiter.hit("user", "ip-a", self.now, "fail", "invalid_credentials")
        later = self.now + timedelta(minutes=16)
        self.assertIsNone(self.limiter.check("user", "ip-b", later))

    def test_disabled_limiter_stays_open(self) -> None:
        limiter = WindowLimiter(MemoryAttempts(), enabled=False)
        for _ in range(30):
            limiter.hit("user", "ip-same", self.now, "fail", "invalid_credentials")
        self.assertIsNone(limiter.check("user", "ip-same", self.now))
