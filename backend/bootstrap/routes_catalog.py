"""Catalog HTTP. The caller must already be signed in."""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.bootstrap.http_errors import error_response
from backend.catalog.api import ApprovalSnapshot, resolved_space
from backend.catalog.application.import_book import import_book
from backend.catalog.application.publish_version import publish_version, retire_version, revise_text
from backend.identity.application.guard import admin_only, signed_in
from backend.kernel.result import Err
from backend.kernel.use_log import read_store


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
    answer_space: str = ""
    answer_space_is_default: bool = True
    formula_note: str = ""


class CatalogListResponse(BaseModel):
    items: list[CatalogItem]


class BookImportBody(BaseModel):
    """Known keys only. Extra keys stay visible so the use case can reject them."""

    model_config = ConfigDict(extra="allow")

    subject_id: str
    dry_run: bool = False
    pages: list[dict[str, Any]]
    pairing: list[dict[str, Any]] = []
    answer_space: list[dict[str, Any]] = []


class BookPageReport(BaseModel):
    pdf_page: int | None
    role: str
    outcome: str
    reason: str


class BookQuestionReport(BaseModel):
    original_key: str
    key: str
    question_version_id: str
    outcome: str
    reason: str


class BookImportResponse(BaseModel):
    book_id: str
    dry_run: bool
    written: bool
    reason: str
    pages: list[BookPageReport]
    questions: list[BookQuestionReport]
    staged: int
    kept: int
    skipped: int
    conflict: int
    space_changed: int = 0


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
                    answer_space=_space_value(row),
                    answer_space_is_default=_space_default(row),
                    formula_note=_formula_note(row),
                )
                for row in rows
            ]
        )
        return JSONResponse(body.model_dump())

    @app.post("/api/admin/catalog/books/{book_id}/import", response_model=BookImportResponse)
    def catalog_import_book(book_id: str, body: BookImportBody, request: Request) -> JSONResponse:
        refused = admin_only(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        loop = request.app.state.loop
        request_id = request.state.request_id
        started = time.perf_counter()
        saved = read_store(
            lambda: import_book(
                book_id,
                body.subject_id,
                body.pages,
                body.pairing,
                loop.questions,
                loop.answers,
                loop.approvals,
                loop.logger,
                request_id,
                dry_run=body.dry_run,
                unknown_fields=bool(body.model_extra),
                actor_user_id=getattr(request.state.actor, "user_id", ""),
                answer_space=body.answer_space,
            ),
            loop.logger,
            request_id,
            "catalog.import_book",
            started,
        )
        if isinstance(saved, Err):
            return error_response(request_id, saved)
        return JSONResponse(saved.value.as_dict())

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
        "answer_space": _space_value(snapshot),
        "answer_space_is_default": _space_default(snapshot),
        "formula_note": _formula_note(snapshot),
    }


def _formula_note(snapshot: ApprovalSnapshot) -> str:
    """Empty when this row stored text and math separately. Old rows say so."""
    if snapshot.stem_parts is not None:
        return ""
    return "公式未结构化"


def _space_value(snapshot: ApprovalSnapshot) -> str:
    value, _default = resolved_space(snapshot.answer_space, snapshot.type)
    return value


def _space_default(snapshot: ApprovalSnapshot) -> bool:
    _value, default = resolved_space(snapshot.answer_space, snapshot.type)
    return default
