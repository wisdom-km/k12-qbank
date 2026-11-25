"""HTTP entry. The actor comes from the server session, not from the body."""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.bootstrap.compose import Loop, attach_identity, compose, repo_root
from backend.bootstrap.ready import ReadyWindow, database_ready
from backend.ai.application.recognize import recover_open_runs
from backend.bootstrap.run_mode import (
    choose_persist,
    cors_origins,
    require_ai_provider,
    require_paper_layout,
    require_pdf_font,
)
from backend.bootstrap.stdout_log import StdoutLogger
from backend.bootstrap.http_errors import error_response
from backend.bootstrap.http_gate import gate
from backend.bootstrap.routes_admin import register_admin
from backend.bootstrap.routes_catalog import register_catalog
from backend.bootstrap.routes_observability import register_observability
from backend.bootstrap.routes_ai import register_ai
from backend.bootstrap.routes_intake import register_intake
from backend.bootstrap.routes_decision import register_decision
from backend.bootstrap.routes_practice import register_practice
from backend.bootstrap.routes_session import register_session
from backend.bootstrap.seed import bootstrap_from_env, load_fixture
from backend.kernel.result import Err
from backend.kernel.use_log import emit

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_WEB = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"


def create_app(
    loop: Loop | None = None,
    *,
    seed: bool = True,
    openapi: bool | None = None,
    persist: bool = False,
) -> FastAPI:
    """Build the HTTP app. persist=True connects and migrates. A passed loop never does."""
    require_ai_provider(os.environ.get("K12_ENV", ""), StdoutLogger())
    origins = cors_origins(
        os.environ.get("K12_ENV", ""),
        os.environ.get("K12_CORS_ORIGINS"),
        StdoutLogger(),
    )
    wired = _wire(loop, persist)
    if seed:
        load_fixture(wired)
    bootstrap_from_env(wired)
    recover_open_runs(wired.ai_runs)
    app = _fastapi(_openapi_on(openapi))
    app.state.loop = wired
    app.state.opener = wired.opener
    app.state.deps = wired.deps
    app.state.errors = wired.errors
    app.state.ready_limit = ReadyWindow()
    app.state.ready_probe = _ready_probe(wired, persist)
    _middleware(app, wired)
    _cors(app, origins)
    register_observability(app)
    register_session(app)
    register_admin(app)
    register_catalog(app)
    register_practice(app)
    register_decision(app)
    register_intake(app)
    register_ai(app)
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

    for path in ("/", "/login", "/admin", "/account"):
        app.add_api_route(path, page, methods=["GET"], include_in_schema=False)


def _wire(loop: Loop | None, persist: bool) -> Loop:
    if not persist:
        return attach_identity(loop) if loop is not None else compose()
    from backend.bootstrap.pg_runtime import open_postgres

    return open_postgres()


def _ready_probe(wired: Loop, persist: bool) -> Callable[[], bool]:
    """Memory mode is not ready. A database mode checks the shipped migrations."""
    if not persist:
        return lambda: False
    pool = wired.identity
    root = repo_root()
    return lambda: database_ready(pool, root)


def _openapi_on(openapi: bool | None) -> bool:
    """None follows K12_OPENAPI. Only the value 1 opens the document."""
    if openapi is not None:
        return openapi
    return os.environ.get("K12_OPENAPI", "0") == "1"


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


_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
_PERMISSIONS = "camera=(), microphone=(), geolocation=(), interest-cohort=()"


def _headers(response: object, request_id: str) -> None:
    headers = response.headers  # type: ignore[attr-defined]
    headers["X-Request-Id"] = request_id
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Cache-Control"] = "no-store"
    if os.environ.get("K12_SECURITY_HEADERS", "1") != "0":
        headers["Content-Security-Policy"] = _CSP
        headers["Permissions-Policy"] = _PERMISSIONS


def _cors(app: FastAPI, origins: tuple[str, ...]) -> None:
    """Credentials stay on. Methods and headers are the ones the page already sends."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Accept", "Content-Type", "X-K12-CSRF", "X-K12-Qr"],
    )


def _default_app() -> FastAPI:
    logger = StdoutLogger()
    env = os.environ.get("K12_ENV", "")
    persist = choose_persist(env, os.environ.get("K12_PG_DSN", ""), logger)
    cors_origins(env, os.environ.get("K12_CORS_ORIGINS"), logger)
    require_pdf_font(env, logger)
    require_paper_layout(env, logger)
    if persist:
        return create_app(persist=True)
    return create_app()


app = _default_app()
