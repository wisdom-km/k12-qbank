"""Intake HTTP. The body is the image bytes. The page does not choose the teacher."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from backend.bootstrap.http_errors import error_response
from backend.kernel.result import Err
from backend.practice.application.intake_photo import (
    intake_max_bytes,
    intake_status,
    read_intake_image,
    upload_intake,
)


def register_intake(app: FastAPI) -> None:
    @app.put("/api/practice/papers/{paper_id}/pages/{page_no}/intake")
    async def upload(paper_id: str, page_no: int, request: Request) -> JSONResponse:
        body, blocked = await _body(request)
        if blocked is not None:
            return error_response(request.state.request_id, blocked)
        loop = request.app.state.loop
        actor = request.state.actor
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        qr_text = request.headers.get("x-k12-qr") or request.query_params.get("qr") or ""
        result = upload_intake(
            paper_id=paper_id,
            page_no=page_no,
            body=body,
            content_type=content_type,
            located_by=request.query_params.get("located_by", ""),
            qr_text=qr_text,
            replace=request.query_params.get("replace", "") == "true",
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            practice=loop.practice,
            items=loop.items,
            files=loop.files,
            intake=loop.intake,
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        return JSONResponse(result.value)

    @app.get("/api/practice/papers/{paper_id}/intake")
    def status(paper_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        actor = request.state.actor
        result = intake_status(
            paper_id=paper_id,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            practice=loop.practice,
            items=loop.items,
            intake=loop.intake,
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        return JSONResponse(result.value)

    @app.get("/api/practice/intake/{intake_id}/image")
    def image(intake_id: str, request: Request) -> Response:
        loop = request.app.state.loop
        actor = request.state.actor
        result = read_intake_image(
            intake_id=intake_id,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            practice=loop.practice,
            files=loop.files,
            intake=loop.intake,
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        data, media = result.value
        return Response(content=data, media_type=media, headers={"Cache-Control": "no-store"})


async def _body(request: Request) -> tuple[bytes, Err | None]:
    limit = intake_max_bytes()
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError:
            return b"", Err("not_image", "not_image")
        if size > limit:
            return b"", Err("too_large", "too_large")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            return b"", Err("too_large", "too_large")
        chunks.append(chunk)
    return b"".join(chunks), None
