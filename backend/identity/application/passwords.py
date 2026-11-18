"""A person changes their own password. An admin resets a teacher."""

from __future__ import annotations

from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only, signed_in
from backend.identity.application.notes import note, started
from backend.identity.application.sessions import revoke_all_sessions_for
from backend.identity.domain.rules import password_ok
from backend.kernel.result import Err, Ok


def change_own_password(db: object, actor: object, old_secret: str, new_secret: str, deps: Deps, request_id: str) -> Ok[None] | Err:
    mark = started()
    refused = signed_in(actor)
    if refused is not None:
        note(deps, request_id, mark, action="change_own_password", actor=actor, target_kind="user", target_id="", outcome="err", reason_code="permission_denied")
        return refused
    user = db.users.by_id(actor.user_id)  # type: ignore[attr-defined]
    if user is None or not deps.hasher.verify(old_secret, user.password_hash):
        note(deps, request_id, mark, action="change_own_password", actor=actor, target_kind="user", target_id=actor.user_id, outcome="err", reason_code="invalid_credentials")
        return Err("invalid_credentials", "invalid_credentials")
    if not password_ok(new_secret):
        note(deps, request_id, mark, action="change_own_password", actor=actor, target_kind="user", target_id=actor.user_id, outcome="err", reason_code="weak_password")
        return Err("weak_password", "weak_password")
    db.users.update_password(user.user_id, deps.hasher.hash(new_secret), "argon2id", deps.clock.now())  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="change_own_password", actor=actor, target_kind="user", target_id=user.user_id, outcome="ok")
    return Ok(None)


def reset_teacher_password(db: object, actor: object, teacher_id: str, secret: str, deps: Deps, request_id: str) -> Ok[None] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action="reset_teacher_password", actor=actor, target_kind="user", target_id=teacher_id, outcome="err", reason_code="permission_denied")
        return refused
    if not password_ok(secret):
        note(deps, request_id, mark, action="reset_teacher_password", actor=actor, target_kind="user", target_id=teacher_id, outcome="err", reason_code="weak_password")
        return Err("weak_password", "weak_password")
    user = db.users.by_id(teacher_id)  # type: ignore[attr-defined]
    if user is None or user.role != "teacher":
        note(deps, request_id, mark, action="reset_teacher_password", actor=actor, target_kind="user", target_id=teacher_id, outcome="err", reason_code="not_found")
        return Err("not_found", "not_found")
    db.users.update_password(teacher_id, deps.hasher.hash(secret), "argon2id", deps.clock.now())  # type: ignore[attr-defined]
    revoked = revoke_all_sessions_for(db, actor, teacher_id, deps, request_id)
    if isinstance(revoked, Err):
        return revoked
    note(deps, request_id, mark, action="reset_teacher_password", actor=actor, target_kind="user", target_id=teacher_id, outcome="ok")
    return Ok(None)
