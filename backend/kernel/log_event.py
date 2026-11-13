"""One log line. Plain data. No I/O and no concrete logging library."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LogEvent:
    time: str
    level: str
    event: str
    request_id: str
    module: str
    outcome: str
    duration_ms: int

    def fields(self) -> dict[str, str | int]:
        return asdict(self)
