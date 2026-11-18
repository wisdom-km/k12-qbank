"""Session and CSRF gate. Health and login stay open. Static files stay open."""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.bootstrap.http_errors import error_response, run_use
from backend.identity.api import Actor
from backend.identity.application.login import load_session
from backend.kernel.result import Err, Ok

_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
_MAX_BODY = 1_048_576
_WHILE_CHANGING = {
    ("GET", "/api/session"),
    ("POST", "/api/logout"),
    ("POST", "/api/account/password"),
}


def gate(request: Request) -> JSONResponse | None:
    if _too_big(request):
        return error_response(request.state.request_id, Err("payload_too_large", "payload_too_large"))
    if _public(request):
        request.state.actor = None
        request.state.session = None
        return None
    user, session, failed = _session(request)
    if failed:
        return error_response(request.state.request_id, Err("store_failed", "the store failed"), status=500)
    if user is None or session is None:
        return error_response(request.state.request_id, Err("unauthenticated", "sign in"))
    if _password_blocked(request, user):
        return error_response(request.state.request_id, Err("password_change_required", "password_change_required"))
    if request.method in _WRITE and not _csrf_ok(request, session.csrf_token):
        return error_response(request.state.request_id, Err("csrf", "csrf"))
    request.state.actor = Actor(user.user_id, user.role, user.username)
    request.state.session = session
    return None


def _password_blocked(request: Request, user: object) -> bool:
    if not getattr(user, "must_change_password", False):
        return False
    return (request.method, request.url.path) not in _WHILE_CHANGING


def _public(request: Request) -> bool:
    path = request.url.path
    if path == "/health" and request.method == "GET":
        return True
    if path == "/api/login" and request.method == "POST":
        return True
    return not path.startswith("/api/")


def _too_big(request: Request) -> bool:
    raw = request.headers.get("content-length")
    if raw is None:
        return False
    try:
        size = int(raw)
    except ValueError:
        return True
    return size > _MAX_BODY


def _csrf_ok(request: Request, token: str) -> bool:
    header = request.headers.get("x-k12-csrf") or ""
    if len(header) != len(token):
        return False
    return secrets.compare_digest(header, token)


def _session(request: Request) -> tuple[object | None, object | None, bool]:
    sid = request.cookies.get("k12_sid", "")
    if not sid:
        return None, None, False
    found: dict[str, object] = {}

    def work(db: object) -> Ok[object] | Err:
        row = load_session(db, sid, request.app.state.deps)
        if row is None:
            return Ok(None)
        found["session"] = row
        found["user"] = db.users.by_id(row.user_id)  # type: ignore[attr-defined]
        return Ok(row)

    result = run_use(request, work)
    if isinstance(result, Err):
        return None, None, True
    user = found.get("user")
    session = found.get("session")
    if user is None or session is None:
        return None, None, False
    return user, session, False
