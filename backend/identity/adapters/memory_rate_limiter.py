"""Sliding windows. Account: 5 failures / 15 minutes. IP: 20 attempts / minute."""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.identity.application.ports import LoginAttemptStore


class WindowLimiter:
    def __init__(
        self,
        attempts: LoginAttemptStore,
        *,
        account_limit: int = 5,
        account_window: timedelta = timedelta(minutes=15),
        ip_limit: int = 20,
        ip_window: timedelta = timedelta(minutes=1),
        enabled: bool = True,
    ) -> None:
        self._attempts = attempts
        self._account_limit = account_limit
        self._account_window = account_window
        self._ip_limit = ip_limit
        self._ip_window = ip_window
        self._enabled = enabled

    def check(self, username_hash: str, ip_hash: str, now: datetime) -> str | None:
        if not self._enabled:
            return None
        if self._attempts.count_ip(ip_hash, now - self._ip_window) >= self._ip_limit:
            return "ip_throttled"
        if self._attempts.count_fails(username_hash, now - self._account_window) >= self._account_limit:
            return "account_locked"
        return None

    def hit(self, username_hash: str, ip_hash: str, now: datetime, outcome: str, reason_code: str) -> None:
        self._attempts.add(username_hash, ip_hash, now, outcome, reason_code)
