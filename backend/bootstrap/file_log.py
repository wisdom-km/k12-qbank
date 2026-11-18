"""JSON Lines runtime log. Daily files, a size cap, and retention. Stdlib only."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.kernel.log_event import LogEvent

MAX_BYTES = 50 * 1024 * 1024


class FileLog:
    def __init__(
        self,
        directory: Path,
        *,
        max_bytes: int = MAX_BYTES,
        retain_days: int = 14,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._directory = Path(directory)
        self._max_bytes = max_bytes
        self._retain_days = retain_days
        self._clock = clock or _utc_now
        self._directory.mkdir(parents=True, exist_ok=True)

    def log(self, event: LogEvent) -> None:
        self.purge()
        payload = _line(event)
        path = self._active()
        if path.exists() and path.stat().st_size + len(payload) > self._max_bytes:
            self._rotate(path)
        with self._active().open("ab") as handle:
            handle.write(payload)

    def purge(self) -> int:
        cutoff = self._clock() - timedelta(days=self._retain_days)
        removed = 0
        for path in self._directory.glob("runtime-*.jsonl"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink()
                removed += 1
        return removed

    def _active(self) -> Path:
        day = self._clock().strftime("%Y%m%d")
        return self._directory / f"runtime-{day}.jsonl"

    def _rotate(self, path: Path) -> None:
        stamp = self._clock().strftime("%H%M%S")
        target = self._unique(path.with_name(f"{path.stem}-{stamp}.jsonl"))
        path.replace(target)
        notice = LogEvent(
            time=self._clock().strftime("%Y-%m-%dT%H:%M:%SZ"),
            level="INFO",
            event="log_rotation",
            request_id="log",
            module="file_log",
            outcome="rotated",
            duration_ms=0,
        )
        with self._active().open("ab") as handle:
            handle.write(_line(notice))

    def _unique(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        for number in range(1, 1000):
            candidate = path.with_name(f"{stem}-{number}.jsonl")
            if not candidate.exists():
                return candidate
        raise OSError("too many rotated log files")


def _line(event: LogEvent) -> bytes:
    return (json.dumps(event.fields(), ensure_ascii=False) + "\n").encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
