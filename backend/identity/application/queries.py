"""Read audit rows and recent errors. Admin only."""

from __future__ import annotations

import json
from datetime import timedelta

from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.application.notes import note, started
from backend.identity.domain.records import AuditRecord
from backend.kernel.result import Err, Ok


def list_audit_events(
    db: object,
    actor: object,
    deps: Deps,
    request_id: str,
    *,
    limit: int,
    offset: int,
    action: str,
    actor_user_id: str,
    since: object,
    until: object,
) -> Ok[tuple[tuple[AuditRecord, ...], int]] | Err:
    refused = admin_only(actor)
    if refused is not None:
        return refused
    bounded = _bound(limit)
    clamped = max(offset, 0)
    names = _filters(action, actor_user_id, since, until)
    _note_read(deps, request_id, actor, "audit", _detail(bounded, clamped, names))
    rows, total = db.audits.list_rows(  # type: ignore[attr-defined]
        limit=bounded,
        offset=clamped,
        action=action,
        actor_user_id=actor_user_id,
        since=since,
        until=until,
    )
    return Ok((rows, total))


def list_recent_errors(
    actor: object,
    errors: object,
    deps: Deps,
    request_id: str,
    *,
    limit: int,
    offset: int,
) -> Ok[tuple[tuple[object, ...], int]] | Err:
    refused = admin_only(actor)
    if refused is not None:
        return refused
    bounded = _bound(limit)
    clamped = max(offset, 0)
    _note_read(deps, request_id, actor, "errors", _detail(bounded, clamped, []))
    since = deps.clock.now() - timedelta(hours=24)
    rows, total = errors.since(since, bounded, clamped)  # type: ignore[attr-defined]
    return Ok((rows, total))


def _note_read(deps: Deps, request_id: str, actor: object, kind: str, detail: str) -> None:
    note(
        deps,
        request_id,
        started(),
        action="admin_read_committed",
        actor=actor,
        target_kind=kind,
        target_id="",
        outcome="ok",
        detail=detail,
    )


def _detail(limit: int, offset: int, filters: list[str]) -> str:
    body: dict[str, object] = {"limit": limit, "offset": offset}
    if filters:
        body["filters"] = filters
    return json.dumps(body, ensure_ascii=False)


def _filters(action: str, actor_user_id: str, since: object, until: object) -> list[str]:
    names: list[str] = []
    if action:
        names.append("action")
    if actor_user_id:
        names.append("actor_user_id")
    if since is not None:
        names.append("since")
    if until is not None:
        names.append("until")
    return names


def _bound(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > 200:
        return 200
    return limit
