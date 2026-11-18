"""Audit sink. Rows go to audit_events. A failed write is kept on disk."""

from __future__ import annotations

import json
from pathlib import Path

from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger

_INSERT = """
INSERT INTO audit_events (
    occurred_at, request_id, actor_user_id, actor_role, action,
    target_kind, target_id, reason_code, outcome, detail_json
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s::jsonb
)
"""


class AuditPg:
    def __init__(self, pool: object, runtime: Logger, fallback: Path) -> None:
        self._pool = pool
        self._runtime = runtime
        self._fallback = fallback

    def write_audit(self, event: LogEvent) -> None:
        try:
            self._insert(event)
        except Exception as exc:
            wrote = self._write_fallback(event)
            logged = self._report(event)
            if wrote and logged:
                return
            raise RuntimeError("audit write failed and the fallback did not stick") from exc

    def _insert(self, event: LogEvent) -> None:
        detail = json.dumps(
            {"module": event.module, "level": event.level, "event": event.event},
            ensure_ascii=False,
        )
        actor = event.actor_user_id or None
        kind = event.target_kind or None
        target = event.target_id or None
        outcome = event.outcome if event.outcome in {"ok", "err"} else "err"
        reason = event.reason_code or None
        role = event.actor_role or None
        action = event.action or event.event
        with self._pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                conn.execute(
                    _INSERT,
                    (
                        event.time,
                        event.request_id,
                        actor,
                        role,
                        action,
                        kind,
                        target,
                        reason,
                        outcome,
                        detail,
                    ),
                )

    def _write_fallback(self, event: LogEvent) -> bool:
        try:
            self._fallback.parent.mkdir(parents=True, exist_ok=True)
            with self._fallback.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.fields(), ensure_ascii=False) + "\n")
            return True
        except OSError:
            return False

    def _report(self, event: LogEvent) -> bool:
        notice = LogEvent(
            time=event.time,
            level="ERROR",
            event="audit_write_failed",
            request_id=event.request_id,
            module="audit_pg",
            outcome="err",
            duration_ms=0,
        )
        try:
            self._runtime.log(notice)
        except Exception:
            return False
        return True
