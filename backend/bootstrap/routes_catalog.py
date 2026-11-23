"""Catalog HTTP. The caller must already be signed in."""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.bootstrap.http_errors import error_response
from backend.catalog.api import ApprovalSnapshot
from backend.catalog.application.import_answer import import_answer_draft
from backend.catalog.application.import_draft import import_question_draft
from backend.catalog.application.publish_version import publish_version, retire_version, revise_text
from backend.catalog.application.stage_review import stage_review, subject_accepted
from backend.identity.application.guard import admin_only, signed_in
from backend.kernel.result import Err
from backend.kernel.use_log import emit


class ReviseBody(BaseModel):
    stem: str
    answer_text: str


class CatalogItem(BaseModel):
    question_version_id: str
    subject_id: str
    stem: str
    answer_text: str
    question_approved: bool
    answer_approved: bool
    retired: bool


class CatalogListResponse(BaseModel):
    items: list[CatalogItem]


class DraftImportBody(BaseModel):
    subject_id: str
    questions: dict[str, Any]
    answers: list[dict[str, Any]]


class DraftImportResponse(BaseModel):
    staged: list[str]
    kept: list[str]
    skipped: list[str]


def register_catalog(app: FastAPI) -> None:
    @app.get("/api/catalog", response_model=CatalogListResponse)
    def catalog_list(request: Request) -> JSONResponse:
        refused = signed_in(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        rows = request.app.state.loop.approvals.list_snapshots()
        body = CatalogListResponse(
            items=[
                CatalogItem(
                    question_version_id=row.question_version_id,
                    subject_id=row.subject_id,
                    stem=row.stem,
                    answer_text=row.answer_text,
                    question_approved=row.question_approved,
                    answer_approved=row.answer_approved,
                    retired=row.retired,
                )
                for row in rows
            ]
        )
        return JSONResponse(body.model_dump())

    @app.post("/api/admin/catalog/drafts", response_model=DraftImportResponse)
    def catalog_import(body: DraftImportBody, request: Request) -> JSONResponse:
        refused = admin_only(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        if not subject_accepted(body.subject_id):
            return error_response(request.state.request_id, Err("validation_failed", "validation_failed"))
        loop = request.app.state.loop
        request_id = request.state.request_id
        imported = import_question_draft(body.questions, loop.questions, loop.logger, request_id)
        if isinstance(imported, Err):
            return error_response(request_id, imported)
        stored = []
        for payload in body.answers:
            saved = import_answer_draft(payload, loop.answers, loop.logger, request_id)
            if isinstance(saved, Err):
                return error_response(request_id, saved)
            stored.append(saved.value)
        staged = stage_review(imported.value, tuple(stored), loop.approvals, body.subject_id)
        emit(
            loop.logger,
            level="INFO",
            event="import_review",
            request_id=request_id,
            module="catalog.import",
            outcome="ok",
            started=time.perf_counter(),
            actor_user_id=getattr(request.state.actor, "user_id", ""),
            target_kind="catalog",
            target_id="",
            audit=True,
        )
        result = DraftImportResponse(staged=list(staged.staged), kept=list(staged.kept), skipped=list(staged.skipped))
        return JSONResponse(result.model_dump())

    @app.get("/api/catalog/{question_version_id}")
    def catalog_get(question_version_id: str, request: Request) -> JSONResponse:
        snapshot = request.app.state.loop.approvals.read_snapshot(question_version_id)
        if snapshot is None:
            return error_response(request.state.request_id, Err("not_found", "the question version does not exist"))
        return JSONResponse(_snapshot_body(snapshot))

    @app.post("/api/catalog/{question_version_id}/publish")
    def catalog_publish(question_version_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        result = publish_version(
            question_version_id,
            loop.approvals,
            loop.logger,
            request.state.request_id,
            publications=loop.publications,
        )
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
