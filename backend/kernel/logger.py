"""Logger port. Runtime sinks and the audit sink are separate."""

from __future__ import annotations

from typing import Protocol

from backend.kernel.log_event import LogEvent


class Logger(Protocol):
    def log(self, event: LogEvent) -> None:
        """Record one structured event. Implementations must not raise into core."""


class AuditSink(Protocol):
    def write_audit(self, event: LogEvent) -> None:
        """Persist one audit event. A failure is reported on the runtime stream."""


class CompositeLogger:
    """Send audit events to the audit sink and everything else to runtime sinks."""

    def __init__(self, runtime: list[Logger], audit: AuditSink, errors: object | None = None) -> None:
        self._runtime = list(runtime)
        self._audit = audit
        self.errors = errors

    def log(self, event: LogEvent) -> None:
        if event.audit:
            self._audit.write_audit(event)
            return
        if self.errors is not None:
            self.errors.add(event)  # type: ignore[attr-defined]
        for sink in self._runtime:
            sink.log(event)
