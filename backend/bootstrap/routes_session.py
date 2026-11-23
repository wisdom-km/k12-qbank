"""Login, logout, and the current session. The cookie is HttpOnly."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.bootstrap.http_errors import error_response, run_use
from backend.bootstrap.synthetic import QUESTION_VERSION_ID
from backend.identity.api import LoginCommand
from backend.identity.application.client_hash import client_hashes
from backend.identity.application.login import login, logout
from backend.identity.application.passwords import change_own_password
from backend.identity.application.sessions import list_own_sessions
from backend.bootstrap.routes_admin import _student_body
from backend.identity.application.students import get_visible_student, list_visible_students
from backend.identity.application.synthetic_seed import session_students
from backend.kernel.result import Err, Ok


class LoginBody(BaseModel):
    username: str
    secret: str


class PasswordBody(BaseModel):
    old_secret: str
    new_secret: str


def register_session(app: FastAPI) -> None:
    @app.post("/api/login")
    def sign_in(body: LoginBody, request: Request) -> JSONResponse:
        return _sign_in(body, request)

    @app.post("/api/logout")
    def sign_out(request: Request) -> JSONResponse:
        return _sign_out(request)

    @app.get("/api/session")
    def current(request: Request) -> JSONResponse:
        return _current(request)

    @app.post("/api/account/password")
    def password(body: PasswordBody, request: Request) -> JSONResponse:
        return _password(body, request)

    @app.get("/api/account/sessions")
    def own_sessions(request: Request) -> JSONResponse:
        return _own_sessions(request)

    @app.get("/api/students")
    def students_visible(request: Request) -> JSONResponse:
        return _students_visible(request)

    @app.get("/api/students/{student_id}")
    def student_visible(student_id: str, request: Request) -> JSONResponse:
        return _student_visible(student_id, request)


def _sign_in(body: LoginBody, request: Request) -> JSONResponse:
    host = request.client.host if request.client is not None else ""
    agent = request.headers.get("user-agent", "")
    user_hash, ip_hash, agent_hash = client_hashes(body.username, host, agent)
    command = LoginCommand(body.username, body.secret, user_hash, ip_hash, agent_hash)
    deps = request.app.state.deps

    def work(db: object) -> Ok[object] | Err:
        signed = login(db, command, deps, request.state.request_id)
        if isinstance(signed, Err):
            return signed
        session = signed.value
        user = db.users.by_id(session.user_id)  # type: ignore[attr-defined]
        students = session_students(db, session.user_id)
        return Ok((user, session, students))

    result = run_use(request, work)
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    user, session, students = result.value  # type: ignore[misc]
    response = JSONResponse(_session_body(user, session, students))
    _cookie(response, session.session_id)
    return response


def _sign_out(request: Request) -> JSONResponse:
    actor = request.state.actor
    session = request.state.session
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: logout(db, actor, session.session_id, deps, request.state.request_id),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    response = JSONResponse({"ok": True})
    response.delete_cookie("k12_sid", path="/")
    return response


def _current(request: Request) -> JSONResponse:
    actor = request.state.actor
    session = request.state.session

    def work(db: object) -> Ok[object] | Err:
        user = db.users.by_id(actor.user_id)  # type: ignore[attr-defined]
        return Ok((user, session_students(db, actor.user_id)))

    result = run_use(request, work)
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    user, students = result.value  # type: ignore[misc]
    return JSONResponse(_session_body(user, session, students))


def _own_sessions(request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(request, lambda db: list_own_sessions(db, actor, deps))
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    rows = [_public_session(row) for row in result.value]  # type: ignore[attr-defined]
    return JSONResponse({"sessions": rows})


def _students_visible(request: Request) -> JSONResponse:
    result = run_use(request, lambda db: list_visible_students(db, request.state.actor))
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"students": [_student_body(row) for row in result.value]})


def _student_visible(student_id: str, request: Request) -> JSONResponse:
    result = run_use(request, lambda db: get_visible_student(db, request.state.actor, student_id))
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse(_student_body(result.value))


def _public_session(row: object) -> dict[str, str]:
    issued = row.issued_at  # type: ignore[attr-defined]
    seen = row.last_seen_at  # type: ignore[attr-defined]
    return {
        "issued_at": issued.isoformat(),
        "last_seen_at": seen.isoformat(),
        "ip_hash_prefix": _hash_prefix(str(row.ip_hash)),  # type: ignore[attr-defined]
    }


def _hash_prefix(value: str) -> str:
    if len(value) < 8:
        return ""
    return value[:8]


def _password(body: PasswordBody, request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: change_own_password(db, actor, body.old_secret, body.new_secret, deps, request.state.request_id),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"ok": True})


def _session_body(user: object, session: object, students: tuple[str, ...]) -> dict[str, object]:
    return {
        "actor_teacher_id": user.user_id,  # type: ignore[attr-defined]
        "user_id": user.user_id,  # type: ignore[attr-defined]
        "role": user.role,  # type: ignore[attr-defined]
        "display_name": user.username,  # type: ignore[attr-defined]
        "csrf_token": session.csrf_token,  # type: ignore[attr-defined]
        "student_ids": list(students),
        "question_version_id": QUESTION_VERSION_ID,
    }


def _cookie(response: JSONResponse, session_id: str) -> None:
    response.set_cookie(
        key="k12_sid",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("K12_SESSION_SECURE") == "1",
        path="/",
    )
