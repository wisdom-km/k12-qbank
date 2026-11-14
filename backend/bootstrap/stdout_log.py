"""Stdout adapter for the logger port. One JSON object per line."""

from __future__ import annotations

import json

from backend.kernel.log_event import LogEvent


class StdoutLogger:
    def log(self, event: LogEvent) -> None:
        print(json.dumps(event.fields(), ensure_ascii=False), flush=True)
