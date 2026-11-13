"""Logger port. The composition root injects a stdout adapter later."""

from __future__ import annotations

from typing import Protocol

from backend.kernel.log_event import LogEvent


class Logger(Protocol):
    def log(self, event: LogEvent) -> None:
        """Record one structured event. Implementations must not raise into core."""
