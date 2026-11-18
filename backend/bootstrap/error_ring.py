"""Recent ERROR events for the admin read. Not an audit log."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone

from backend.bootstrap.stdout_log import StdoutLogger
from backend.kernel.log_event import LogEvent

_FIELDS = ("time", "request_id", "module", "event", "outcome")
_TIMEOUT_SECONDS = 2
_ATTEMPTS = 2
_Poster = Callable[[str, bytes], None]


class ErrorRing:
    def __init__(self, *, poster: _Poster | None = None, url: str | None = None) -> None:
        self.rows: list[LogEvent] = []
        self._poster = poster
        self._url = url
        self._pending: list[threading.Thread] = []
        self._lock = threading.Lock()

    def add(self, event: LogEvent) -> None:
        if event.level != "ERROR" or event.audit:
            return
        self.rows.append(event)
        self._schedule(event)

    def since(self, moment: datetime, limit: int, offset: int) -> tuple[tuple[LogEvent, ...], int]:
        chosen = [row for row in self.rows if _stamp(row.time) >= moment]
        return tuple(chosen[offset : offset + limit]), len(chosen)

    def wait(self, timeout: float = 5) -> None:
        """Join webhook attempts. Callers of add do not need this."""
        for thread in self._snapshot():
            thread.join(timeout)

    def _schedule(self, event: LogEvent) -> None:
        url = self._target()
        if not url:
            return
        body = {name: str(getattr(event, name)) for name in _FIELDS}
        thread = threading.Thread(
            target=_deliver,
            args=(url, body, event.request_id, self._poster),
            daemon=True,
        )
        with self._lock:
            self._pending = [item for item in self._pending if item.is_alive()]
            self._pending.append(thread)
        thread.start()

    def _target(self) -> str:
        if self._url is not None:
            return self._url.strip()
        return os.environ.get("K12_ERROR_WEBHOOK_URL", "").strip()

    def _snapshot(self) -> list[threading.Thread]:
        with self._lock:
            return list(self._pending)


def _deliver(url: str, body: dict[str, str], request_id: str, poster: _Poster | None) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    send = _post if poster is None else poster
    for _attempt in range(_ATTEMPTS):
        try:
            send(url, payload)
            return
        except Exception:
            continue
    _warn(request_id)


def _post(url: str, payload: bytes) -> None:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        response.read()


def _warn(request_id: str) -> None:
    """One stdout WARN. This does not go back through the ring."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    StdoutLogger().log(
        LogEvent(
            time=now,
            level="WARN",
            event="webhook_failed",
            request_id=request_id,
            module="bootstrap",
            outcome="gave_up",
            duration_ms=0,
        )
    )


def _stamp(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return parsed.replace(tzinfo=timezone.utc)
