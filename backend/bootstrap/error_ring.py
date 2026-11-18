"""Recent ERROR events for the admin read. Not an audit log."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.kernel.log_event import LogEvent


class ErrorRing:
    def __init__(self) -> None:
        self.rows: list[LogEvent] = []

    def add(self, event: LogEvent) -> None:
        if event.level == "ERROR" and not event.audit:
            self.rows.append(event)

    def since(self, moment: datetime, limit: int, offset: int) -> tuple[tuple[LogEvent, ...], int]:
        chosen = [row for row in self.rows if _stamp(row.time) >= moment]
        return tuple(chosen[offset : offset + limit]), len(chosen)


def _stamp(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return parsed.replace(tzinfo=timezone.utc)
