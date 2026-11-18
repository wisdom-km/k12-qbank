"""HTTP error bodies. Login failures stay generic."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from backend.identity.application.run import execute
from backend.kernel.result import Err, Ok

_STATUS = {
    "invalid_credentials": 401,
    "unauthenticated": 401,
    "permission_denied": 403,
    "csrf": 403,
    "account_locked": 429,
    "ip_throttled": 429,
    "validation_failed": 400,
    "weak_password": 400,
    "not_found": 404,
    "snapshot_not_found": 404,
    "paper_not_found": 404,
    "file_missing": 404,
    "username_taken": 409,
    "slot_conflict": 409,
    "already_granted": 409,
    "not_granted": 409,
    "payload_too_large": 413,
}
_GENERIC = {"invalid_credentials", "unauthenticated"}


def error_response(request_id: str, err: Err, status: int | None = None) -> JSONResponse:
    status = _STATUS.get(err.code, 409) if status is None else status
    if err.code in _GENERIC:
        code, message = "unauthenticated", "sign in"
    else:
        code, message = err.code, err.message
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id},
    )


def run_use(request: object, work: object) -> Ok[object] | Err:
    deps = request.app.state.deps  # type: ignore[attr-defined]
    opener = request.app.state.opener  # type: ignore[attr-defined]
    request_id = request.state.request_id  # type: ignore[attr-defined]
    return execute(opener, work, deps.logger, request_id)  # type: ignore[arg-type]
