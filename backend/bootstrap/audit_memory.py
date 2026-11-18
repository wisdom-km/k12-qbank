"""In-memory audit sink for tests and the synthetic process."""

from __future__ import annotations

from backend.kernel.log_event import LogEvent


class MemoryAudit:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def write_audit(self, event: LogEvent) -> None:
        self.events.append(event)
