"""Disable a user or change a role without dropping the last active admin."""

from __future__ import annotations

from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.application.notes import note, started
from backend.identity.domain.records import User
from backend.identity.domain.rules import ensure_last_admin
from backend.kernel.result import Err, Ok

_ROLES = {"admin", "teacher"}


def disable_user(db: object, actor: object, user_id: str, deps: Deps, request_id: str) -> Ok[None] | Err:
    mark = started()
    user = _known(db, actor, user_id, deps, request_id, mark, "disable_user")
    if isinstance(user, Err):
        return user
    active = db.users.count_active("admin")  # type: ignore[attr-defined]
    blocked = ensure_last_admin(_after_disable(user, active))
    if blocked is not None:
        return _err(deps, request_id, mark, actor, user_id, "disable_user", blocked)
    now = deps.clock.now()
    db.users.set_status(user.user_id, "disabled", now, now)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="disable_user", actor=actor, target_kind="user", target_id=user_id, outcome="ok")
    return Ok(None)


def change_role(db: object, actor: object, user_id: str, role: str, deps: Deps, request_id: str) -> Ok[None] | Err:
    mark = started()
    user = _known(db, actor, user_id, deps, request_id, mark, "change_role")
    if isinstance(user, Err):
        return user
    if role not in _ROLES:
        return _err(deps, request_id, mark, actor, user_id, "change_role", "validation_failed")
    active = db.users.count_active("admin")  # type: ignore[attr-defined]
    blocked = ensure_last_admin(_after_role(user, role, active))
    if blocked is not None:
        return _err(deps, request_id, mark, actor, user_id, "change_role", blocked)
    db.users.set_role(user.user_id, role, deps.clock.now())  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="change_role", actor=actor, target_kind="user", target_id=user_id, outcome="ok")
    return Ok(None)


def _known(db: object, actor: object, user_id: str, deps: Deps, request_id: str, mark: float, action: str) -> User | Err:
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action=action, actor=actor, target_kind="user", target_id=user_id, outcome="err", reason_code="permission_denied")
        return refused
    user = db.users.by_id(user_id)  # type: ignore[attr-defined]
    if user is None:
        return _err(deps, request_id, mark, actor, user_id, action, "not_found")
    return user


def _err(deps: Deps, request_id: str, mark: float, actor: object, user_id: str, action: str, code: str) -> Err:
    note(deps, request_id, mark, action=action, actor=actor, target_kind="user", target_id=user_id, outcome="err", reason_code=code)
    return Err(code, code)


def _after_disable(user: User, active: int) -> int:
    if user.role == "admin" and user.status == "active":
        return active - 1
    return active


def _after_role(user: User, role: str, active: int) -> int:
    was = user.role == "admin" and user.status == "active"
    will = role == "admin" and user.status == "active"
    if was and not will:
        return active - 1
    if will and not was:
        return active + 1
    return active
