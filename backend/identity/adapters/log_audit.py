"""Audit writer. The logger routes audit=True to the audit sink."""

from __future__ import annotations

from datetime import datetime

from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger


class LogAudit:
    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def commit(
        self,
        *,
        request_id: str,
        occurred_at: datetime,
        actor_user_id: str,
        actor_role: str,
        action: str,
        target_kind: str,
        target_id: str,
        outcome: str,
        reason_code: str,
    ) -> None:
        self._logger.log(
            LogEvent(
                time=occurred_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                level="INFO" if outcome == "ok" else "WARN",
                event="admin_action_committed",
                request_id=request_id,
                module="identity",
                outcome=outcome,
                duration_ms=0,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                target_kind=target_kind,
                target_id=target_id,
                reason_code=reason_code,
                action=action,
                audit=True,
            )
        )
