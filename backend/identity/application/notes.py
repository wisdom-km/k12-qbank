"""Audit and runtime notes. No passwords and no session identifiers."""

from __future__ import annotations

import time

from backend.identity.application.deps import Deps
from backend.kernel.use_log import emit


def note(
    deps: Deps,
    request_id: str,
    started: float,
    *,
    action: str,
    actor: object | None,
    target_kind: str,
    target_id: str,
    outcome: str,
    reason_code: str = "",
) -> None:
    deps.audit.commit(
        request_id=request_id,
        occurred_at=deps.clock.now(),
        actor_user_id="" if actor is None else str(getattr(actor, "user_id", "")),
        actor_role="" if actor is None else str(getattr(actor, "role", "")),
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        outcome=outcome,
        reason_code=reason_code,
    )


def runtime(deps: Deps, request_id: str, started: float, event: str, outcome: str) -> None:
    level = "INFO" if outcome == "ok" else "WARN"
    emit(
        deps.logger,
        level=level,
        event=event,
        request_id=request_id,
        module="identity",
        outcome=outcome,
        started=started,
    )


def started() -> float:
    return time.perf_counter()
