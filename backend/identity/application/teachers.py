"""Admin creates and enables or disables teachers."""

from __future__ import annotations

import uuid

from backend.identity.application.conflict import Conflict
from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.application.notes import note, started
from backend.identity.application.sessions import revoke_all_sessions_for
from backend.identity.domain.records import User
from backend.identity.domain.rules import can_disable, can_enable, password_ok, username_ok
from backend.kernel.result import Err, Ok


def create_teacher(db: object, actor: object, username: str, secret: str, deps: Deps, request_id: str) -> Ok[User] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action="create_teacher", actor=actor, target_kind="user", target_id="", outcome="err", reason_code="permission_denied")
        return refused
    if not username_ok(username):
        return _bad(deps, request_id, mark, actor, "", "validation_failed")
    if not password_ok(secret):
        return _bad(deps, request_id, mark, actor, "", "weak_password")
    if db.users.by_username(username) is not None:  # type: ignore[attr-defined]
        return _bad(deps, request_id, mark, actor, "", "username_taken")
    now = deps.clock.now()
    user = User(
        user_id=str(uuid.uuid4()),
        username=username,
        role="teacher",
        status="active",
        password_hash=deps.hasher.hash(secret),
        password_algo="argon2id",
        created_at=now,
        updated_at=now,
    )
    try:
        db.users.insert(user)  # type: ignore[attr-defined]
    except Conflict as exc:
        note(deps, request_id, mark, action="create_teacher", actor=actor, target_kind="user", target_id="", outcome="err", reason_code=exc.code)
        raise
    note(deps, request_id, mark, action="create_teacher", actor=actor, target_kind="user", target_id=user.user_id, outcome="ok")
    return Ok(user)


def disable_teacher(db: object, actor: object, teacher_id: str, deps: Deps, request_id: str) -> Ok[User] | Err:
    return _status(db, actor, teacher_id, "disabled", deps, request_id, "disable_teacher", can_disable)


def enable_teacher(db: object, actor: object, teacher_id: str, deps: Deps, request_id: str) -> Ok[User] | Err:
    return _status(db, actor, teacher_id, "active", deps, request_id, "enable_teacher", can_enable)


def list_teachers(db: object, actor: object, deps: Deps, request_id: str) -> Ok[tuple[User, ...]] | Err:
    refused = admin_only(actor)
    if refused is not None:
        return refused
    return Ok(db.users.list_role("teacher"))  # type: ignore[attr-defined]


def _status(db: object, actor: object, teacher_id: str, status: str, deps: Deps, request_id: str, action: str, allowed) -> Ok[User] | Err:  # type: ignore[no-untyped-def]
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action=action, actor=actor, target_kind="user", target_id=teacher_id, outcome="err", reason_code="permission_denied")
        return refused
    user = db.users.by_id(teacher_id)  # type: ignore[attr-defined]
    if user is None or user.role != "teacher":
        return _bad(deps, request_id, mark, actor, teacher_id, "not_found", action)
    if not allowed(user.status):
        return _bad(deps, request_id, mark, actor, teacher_id, "validation_failed", action)
    now = deps.clock.now()
    disabled_at = now if status == "disabled" else None
    db.users.set_status(teacher_id, status, now, disabled_at)  # type: ignore[attr-defined]
    revoked = revoke_all_sessions_for(db, actor, teacher_id, deps, request_id)
    if isinstance(revoked, Err):
        return revoked
    saved = db.users.by_id(teacher_id)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action=action, actor=actor, target_kind="user", target_id=teacher_id, outcome="ok")
    return Ok(saved)


def _bad(deps: Deps, request_id: str, mark: float, actor: object, target_id: str, code: str, action: str = "create_teacher") -> Err:
    note(deps, request_id, mark, action=action, actor=actor, target_kind="user", target_id=target_id, outcome="err", reason_code=code)
    return Err(code, code)
