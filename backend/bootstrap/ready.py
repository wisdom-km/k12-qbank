"""Readiness is a database check. Liveness stays in health_report."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from backend.bootstrap.migrate import discover


class ReadyWindow:
    """One IP may call readiness 30 times in 60 seconds."""

    def __init__(
        self,
        *,
        limit: int = 30,
        window_s: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock or time.monotonic
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        now = self._clock()
        with self._lock:
            recent = [item for item in self._hits.get(ip, []) if now - item < self._window_s]
            if len(recent) >= self._limit:
                self._hits[ip] = recent
                return False
            recent.append(now)
            self._hits[ip] = recent
            return True


def database_ready(pool: object, root: Path) -> bool:
    """True when SELECT 1 works and the applied set matches the shipped set."""
    try:
        with pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                one = conn.execute("SELECT 1").fetchone()  # type: ignore[attr-defined]
                if one is None or int(one[0]) != 1:
                    return False
                rows = conn.execute(  # type: ignore[attr-defined]
                    """
                    SELECT version FROM schema_migrations
                    ORDER BY applied_at DESC, version DESC
                    """
                ).fetchall()
    except Exception:
        return False
    expected = [item.version for item in discover(root)]
    applied = [str(row[0]) for row in rows]
    if not expected or set(applied) != set(expected):
        return False
    return applied[0] == expected[-1]
