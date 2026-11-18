"""Revoke sessions that have not yet expired, and list the caller's own rows.

The revoke count stays off the audit row. The list writes no audit row.
"""

from __future__ import annotations

from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only, signed_in
from backend.identity.application.notes import note, started
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit


def revoke_all_sessions_for(
    db: object, actor: object, user_id: str, deps: Deps, request_id: str
) -> Ok[int] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        _err(deps, request_id, mark, actor, "permission_denied")
        return refused
    user = db.users.by_id(user_id)  # type: ignore[attr-defined]
    if user is None:
        _err(deps, request_id, mark, actor, "not_found")
        return Err("not_found", "not_found")
    count = int(db.sessions.revoke_unexpired(user_id, deps.clock.now()))  # type: ignore[attr-defined]
    note(
        deps,
        request_id,
        mark,
        action="session_revoked",
        actor=actor,
        target_kind="user",
        target_id="",
        outcome="ok",
    )
    emit(
        deps.logger,
        level="INFO",
        event="session_revoked",
        request_id=request_id,
        module="identity",
        outcome=str(count),
        started=mark,
        actor_user_id="" if actor is None else str(getattr(actor, "user_id", "")),
    )
    return Ok(count)


def list_own_sessions(db: object, actor: object, deps: Deps) -> Ok[tuple[object, ...]] | Err:
    refused = signed_in(actor)
    if refused is not None:
        return refused
    user_id = "" if actor is None else str(getattr(actor, "user_id", ""))
    rows = db.sessions.list_unexpired(user_id, deps.clock.now())  # type: ignore[attr-defined]
    return Ok(tuple(rows))


def _err(deps: Deps, request_id: str, mark: float, actor: object, code: str) -> None:
    note(
        deps,
        request_id,
        mark,
        action="session_revoked",
        actor=actor,
        target_kind="user",
        target_id="",
        outcome="err",
        reason_code=code,
    )
