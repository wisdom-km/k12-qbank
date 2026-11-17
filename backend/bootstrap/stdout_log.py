"""Stdout adapter for the logger port. One JSON object per line."""

from __future__ import annotations

import json
from collections.abc import Callable

from backend.kernel.log_event import LogEvent


class StdoutLogger:
    def __init__(self, sink: Callable[[str], None] | None = None) -> None:
        self._sink = sink or _print_line
        self.degraded: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        """Write one line. A broken sink keeps a degraded line and does not raise."""
        line = json.dumps(event.fields(), ensure_ascii=False)
        try:
            self._sink(line)
        except Exception:
            fallback = LogEvent(
                time=event.time,
                level="ERROR",
                event="log_failed",
                request_id=event.request_id,
                module=event.module,
                outcome="log_degraded",
                duration_ms=event.duration_ms,
            )
            self.degraded.append(fallback)
            try:
                self._sink(json.dumps(fallback.fields(), ensure_ascii=False))
            except Exception:
                return


def _print_line(line: str) -> None:
    print(line, flush=True)
