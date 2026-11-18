"""HTTP entry. The actor comes from the server session, not from the body."""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request

from backend.bootstrap.compose import Loop, attach_identity, compose
from backend.bootstrap.http_errors import error_response
from backend.bootstrap.http_gate import gate
from backend.bootstrap.routes_admin import register_admin
from backend.bootstrap.routes_catalog import register_catalog
from backend.bootstrap.routes_observability import register_observability
from backend.bootstrap.routes_practice import register_practice
from backend.bootstrap.routes_session import register_session
from backend.bootstrap.seed import bootstrap_from_env, load_fixture
from backend.kernel.result import Err
from backend.kernel.use_log import emit

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_WEB = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"


def create_app(loop: Loop | None = None, *, seed: bool = True, openapi: bool = False, persist: bool = False) -> FastAPI:
    """Build the HTTP app. persist=True connects and migrates. A passed loop never does."""
    wired = _wire(loop, persist)
    if seed:
        load_fixture(wired)
    bootstrap_from_env(wired)
    app = _fastapi(openapi)
    app.state.loop = wired
    app.state.opener = wired.opener
    app.state.deps = wired.deps
    app.state.errors = wired.errors
    _middleware(app, wired)
    register_observability(app)
    register_session(app)
    register_admin(app)
    register_catalog(app)
    register_practice(app)
    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    index = _WEB / "index.html"
    if not index.is_file():
        return
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets = _WEB / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="web-assets")

    def page() -> FileResponse:
        return FileResponse(index)

    for path in ("/", "/login", "/admin"):
        app.add_api_route(path, page, methods=["GET"], include_in_schema=False)


def _wire(loop: Loop | None, persist: bool) -> Loop:
    if not persist:
        return attach_identity(loop) if loop is not None else compose()
    from backend.bootstrap.pg_runtime import open_postgres

    return open_postgres()


def _fastapi(openapi: bool) -> FastAPI:
    if openapi:
        return FastAPI(title="k12-qbank")
    return FastAPI(title="k12-qbank", docs_url=None, redoc_url=None, openapi_url=None)


def _middleware(app: FastAPI, wired: Loop) -> None:
    @app.middleware("http")
    async def access(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = _request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            blocked = gate(request)
            response = blocked if blocked is not None else await call_next(request)
        except Exception:
            emit(
                wired.logger,
                level="ERROR",
                event="use_case_failed",
                request_id=request_id,
                module="http",
                outcome="store_failed",
                started=started,
            )
            response = error_response(request_id, Err("store_failed", "the store failed"), status=500)
        route = request.scope.get("route")
        template = getattr(route, "path", "unmatched")
        emit(
            wired.logger,
            level="INFO",
            event="http_completed",
            request_id=request_id,
            module=str(template),
            outcome=str(response.status_code),
            started=started,
        )
        _headers(response, request_id)
        return response


def _request_id(header: str | None) -> str:
    if header and _REQUEST_ID.fullmatch(header):
        return header
    return uuid.uuid4().hex


def _headers(response: object, request_id: str) -> None:
    headers = response.headers  # type: ignore[attr-defined]
    headers["X-Request-Id"] = request_id
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Cache-Control"] = "no-store"


def _default_app() -> FastAPI:
    if os.environ.get("K12_PG_DSN", "").strip():
        return create_app(persist=True)
    return create_app()


app = _default_app()
