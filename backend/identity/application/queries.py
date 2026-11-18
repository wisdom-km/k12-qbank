"""Read audit rows and recent errors. Admin only."""

from __future__ import annotations

from datetime import timedelta

from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.domain.records import AuditRecord
from backend.kernel.result import Err, Ok


def list_audit_events(
    db: object,
    actor: object,
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
    rows, total = db.audits.list_rows(  # type: ignore[attr-defined]
        limit=bounded,
        offset=max(offset, 0),
        action=action,
        actor_user_id=actor_user_id,
        since=since,
        until=until,
    )
    return Ok((rows, total))


def list_recent_errors(actor: object, errors: object, deps: Deps, *, limit: int, offset: int) -> Ok[tuple[tuple[object, ...], int]] | Err:
    refused = admin_only(actor)
    if refused is not None:
        return refused
    since = deps.clock.now() - timedelta(hours=24)
    rows, total = errors.since(since, _bound(limit), max(offset, 0))  # type: ignore[attr-defined]
    return Ok((rows, total))


def _bound(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > 200:
        return 200
    return limit
