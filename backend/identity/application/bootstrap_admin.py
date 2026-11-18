"""Create the first admin once. The secret is not logged."""

from __future__ import annotations

import uuid

from backend.identity.application.deps import Deps
from backend.identity.application.notes import note, started
from backend.identity.domain.records import User
from backend.identity.domain.rules import password_ok, username_ok
from backend.kernel.result import Err, Ok


def bootstrap_admin(db: object, username: str, secret: str, deps: Deps, request_id: str) -> Ok[User | None] | Err:
    mark = started()
    if not username and not secret:
        return Ok(None)
    if db.users.count_role("admin") > 0:  # type: ignore[attr-defined]
        return Ok(None)
    if not username_ok(username) or not password_ok(secret):
        note(deps, request_id, mark, action="bootstrap_admin", actor=None, target_kind="user", target_id="", outcome="err", reason_code="validation_failed")
        return Err("validation_failed", "validation_failed")
    now = deps.clock.now()
    user = User(
        user_id=str(uuid.uuid4()),
        username=username,
        role="admin",
        status="active",
        password_hash=deps.hasher.hash(secret),
        password_algo="argon2id",
        created_at=now,
        updated_at=now,
        must_change_password=True,
    )
    db.users.insert(user)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="bootstrap_admin", actor=None, target_kind="user", target_id=user.user_id, outcome="ok")
    return Ok(user)
