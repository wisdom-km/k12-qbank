"""Catalog HTTP. The caller must already be signed in."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.bootstrap.http_errors import error_response
from backend.catalog.api import ApprovalSnapshot, Publication
from backend.catalog.application.publish_version import publish_version, retire_version, revise_text
from backend.kernel.result import Err


class ReviseBody(BaseModel):
    stem: str
    answer_text: str


def register_catalog(app: FastAPI) -> None:
    @app.get("/api/catalog/{question_version_id}")
    def catalog_get(question_version_id: str, request: Request) -> JSONResponse:
        snapshot = request.app.state.loop.approvals.read_snapshot(question_version_id)
        if snapshot is None:
            return error_response(request.state.request_id, Err("not_found", "the question version does not exist"))
        return JSONResponse(_snapshot_body(snapshot))

    @app.post("/api/catalog/{question_version_id}/publish")
    def catalog_publish(question_version_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        before = loop.approvals.read_snapshot(question_version_id)
        result = publish_version(
            question_version_id,
            loop.approvals,
            loop.logger,
            request.state.request_id,
        )
        if not isinstance(result, Err) and not _already_issuable(before):
            _mirror_grandfather(loop.publications, result.value)
        return _finish(request, result)

    @app.post("/api/catalog/{question_version_id}/revise")
    def catalog_revise(question_version_id: str, body: ReviseBody, request: Request) -> JSONResponse:
        result = revise_text(
            question_version_id,
            body.stem,
            body.answer_text,
            request.app.state.loop.approvals,
            request.app.state.loop.logger,
            request.state.request_id,
        )
        return _finish(request, result)

    @app.post("/api/catalog/{question_version_id}/retire")
    def catalog_retire(question_version_id: str, request: Request) -> JSONResponse:
        result = retire_version(
            question_version_id,
            request.app.state.loop.approvals,
            request.app.state.loop.logger,
            request.state.request_id,
        )
        return _finish(request, result)


def _finish(request: Request, result: object) -> JSONResponse:
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse(_snapshot_body(result.value))  # type: ignore[attr-defined]


def _snapshot_body(snapshot: ApprovalSnapshot) -> dict[str, object]:
    return {
        "question_version_id": snapshot.question_version_id,
        "answer_version_id": snapshot.answer_version_id,
        "subject_id": snapshot.subject_id,
        "stem": snapshot.stem,
        "answer_text": snapshot.answer_text,
        "question_approved": snapshot.question_approved,
        "answer_approved": snapshot.answer_approved,
        "retired": snapshot.retired,
        "item_order": list(snapshot.item_order),
        "asset_ids": list(snapshot.asset_ids),
        "layout_template_id": snapshot.layout_template_id,
    }


def _already_issuable(snapshot: ApprovalSnapshot | None) -> bool:
    """True when this approval was already a grandfather source. A repeat publish must not revive a retired publication."""
    return (
        snapshot is not None
        and snapshot.question_approved
        and snapshot.answer_approved
        and not snapshot.retired
    )


def _mirror_grandfather(publications: object, snapshot: ApprovalSnapshot) -> None:
    """Write the V007 grandfather row when catalog publish first approves both sides."""
    if not snapshot.question_approved or not snapshot.answer_approved or snapshot.retired:
        return
    found = publications.active_of(snapshot.question_version_id, snapshot.answer_version_id)  # type: ignore[attr-defined]
    if found is not None:
        return
    publications.put(  # type: ignore[attr-defined]
        Publication(
            publication_id="pub-" + snapshot.question_version_id + "-" + snapshot.answer_version_id,
            question_version_id=snapshot.question_version_id,
            answer_version_id=snapshot.answer_version_id,
            subject_id=snapshot.subject_id,
            status="active",
        )
    )
