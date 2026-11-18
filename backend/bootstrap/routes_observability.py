"""Liveness, readiness, and the admin error read. Liveness does not check the database."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.bootstrap.health import health_report
from backend.bootstrap.http_errors import error_response
from backend.identity.application.queries import list_recent_errors
from backend.kernel.result import Err


def register_observability(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, str]:
        return _live()

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return _live()

    @app.get("/health/ready")
    def ready(request: Request) -> JSONResponse:
        ip = request.client.host if request.client is not None else ""
        if not request.app.state.ready_limit.allow(ip):
            return error_response(request.state.request_id, Err("ip_throttled", "ip_throttled"))
        if not request.app.state.ready_probe():
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/api/admin/errors")
    def errors(request: Request, limit: int = 50, offset: int = 0) -> JSONResponse:
        result = list_recent_errors(
            request.state.actor,
            request.app.state.errors,
            request.app.state.deps,
            request.state.request_id,
            limit=limit,
            offset=offset,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        rows, total = result.value
        return JSONResponse({"total": total, "errors": [_error_body(row) for row in rows]})


def _live() -> dict[str, str]:
    return {"status": health_report().status}


def _error_body(event: object) -> dict[str, object]:
    return {
        "time": event.time,  # type: ignore[attr-defined]
        "level": event.level,  # type: ignore[attr-defined]
        "event": event.event,  # type: ignore[attr-defined]
        "request_id": event.request_id,  # type: ignore[attr-defined]
        "module": event.module,  # type: ignore[attr-defined]
        "outcome": event.outcome,  # type: ignore[attr-defined]
    }
