"""Login and logout. A successful login rotates the session id."""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from backend.identity.application.deps import Deps
from backend.identity.application.notes import note, runtime, started
from backend.identity.domain.records import Session
from backend.identity.domain.rules import session_usable
from backend.kernel.result import Err, Ok


def login(db: object, command: object, deps: Deps, request_id: str) -> Ok[Session] | Err:
    mark = started()
    username = str(getattr(command, "username", ""))
    secret = str(getattr(command, "secret", ""))
    user_hash = str(getattr(command, "username_hash", ""))
    ip_hash = str(getattr(command, "ip_hash", ""))
    agent_hash = str(getattr(command, "user_agent_hash", ""))
    now = deps.clock.now()
    blocked = deps.limiter.check(user_hash, ip_hash, now)
    if blocked:
        deps.limiter.hit(user_hash, ip_hash, now, "fail", blocked)
        note(deps, request_id, mark, action="login", actor=None, target_kind="user", target_id="", outcome="err", reason_code=blocked)
        runtime(deps, request_id, mark, "login_failed", blocked)
        return Err(blocked, blocked)
    user = db.users.by_username(username)  # type: ignore[attr-defined]
    if user is None or user.status != "active" or not deps.hasher.verify(secret, user.password_hash):
        deps.limiter.hit(user_hash, ip_hash, now, "fail", "invalid_credentials")
        note(deps, request_id, mark, action="login", actor=None, target_kind="user", target_id="", outcome="err", reason_code="invalid_credentials")
        runtime(deps, request_id, mark, "login_failed", "invalid_credentials")
        return Err("invalid_credentials", "invalid_credentials")
    if deps.hasher.needs_rehash(user.password_hash):
        db.users.update_password(user.user_id, deps.hasher.hash(secret), "argon2id", now)  # type: ignore[attr-defined]
    db.sessions.revoke_user(user.user_id, now)  # type: ignore[attr-defined]
    session = Session(
        session_id=str(uuid.uuid4()),
        user_id=user.user_id,
        csrf_token=secrets.token_urlsafe(32),
        issued_at=now,
        last_seen_at=now,
        expires_at=now + deps.absolute,
        user_agent_hash=agent_hash,
        ip_hash=ip_hash,
    )
    db.sessions.put(session)  # type: ignore[attr-defined]
    deps.limiter.hit(user_hash, ip_hash, now, "ok", "")
    actor = _actor(user)
    note(deps, request_id, mark, action="login", actor=actor, target_kind="user", target_id=user.user_id, outcome="ok")
    runtime(deps, request_id, mark, "login_succeeded", "ok")
    return Ok(session)


def logout(db: object, actor: object, session_id: str, deps: Deps, request_id: str) -> Ok[None] | Err:
    mark = started()
    now = deps.clock.now()
    db.sessions.revoke(session_id, now)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="logout", actor=actor, target_kind="user", target_id=getattr(actor, "user_id", ""), outcome="ok")
    runtime(deps, request_id, mark, "session_revoked", "ok")
    return Ok(None)


def load_session(db: object, session_id: str, deps: Deps) -> Session | None:
    row = db.sessions.get(session_id)  # type: ignore[attr-defined]
    if row is None:
        return None
    now = deps.clock.now()
    if session_usable(row.revoked_at, row.expires_at, row.last_seen_at, now, deps.idle):
        db.sessions.touch(session_id, now)  # type: ignore[attr-defined]
        return db.sessions.get(session_id)  # type: ignore[attr-defined]
    db.sessions.revoke(session_id, now)  # type: ignore[attr-defined]
    return None


def _actor(user: object) -> object:
    from backend.identity.api import Actor

    return Actor(user_id=user.user_id, role=user.role, username=user.username)  # type: ignore[attr-defined]


def idle_of(minutes: int) -> timedelta:
    return timedelta(minutes=minutes)
