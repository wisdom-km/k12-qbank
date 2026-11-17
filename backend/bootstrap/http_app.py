"""HTTP entry. The actor comes from the synthetic server context, not from the body."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.bootstrap.compose import Loop, compose
from backend.bootstrap.health import health_report
from backend.bootstrap.seed import load_fixture, synthetic_attempt_text
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, QUESTION_VERSION_ID, STUDENT_IDS
from backend.catalog.api import ApprovalSnapshot
from backend.catalog.application.publish_version import publish_version, retire_version, revise_text
from backend.kernel.result import Err
from backend.kernel.use_log import emit
from backend.practice.api import ConfirmCommand, IssuePaperCommand, Paper
from backend.practice.application.confirm_attempt import confirm_attempt
from backend.practice.application.open_paper import open_paper, read_attempt
from backend.practice.application.render_paper import hand_out_paper, read_file
from backend.practice.application.visible import visible_confirmation_count, visible_papers

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_WEB = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"


class IssueBody(BaseModel):
    teacher_id: str
    student_id: str
    subject_id: str
    question_version_id: str
    review_version_id: str


class ConfirmBody(BaseModel):
    operation_key: str
    paper_id: str
    sub_question_id: str
    teacher_id: str
    review_version_id: str
    decision: str
    fixture_answer_id: str


class ReviseBody(BaseModel):
    stem: str
    answer_text: str


def create_app(loop: Loop | None = None, *, seed: bool = True, openapi: bool = False) -> FastAPI:
    wired = loop if loop is not None else compose()
    if seed:
        load_fixture(wired)
    if openapi:
        app = FastAPI(title="k12-qbank")
    else:
        app = FastAPI(title="k12-qbank", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.loop = wired

    @app.middleware("http")
    async def access(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = _request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
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
            response = _error(request_id, Err("store_failed", "the store failed"), status=500)
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
        response.headers["X-Request-Id"] = request_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        report = health_report()
        return {"status": report.status}

    @app.get("/api/session")
    def session() -> dict[str, object]:
        return {
            "actor_teacher_id": ACTOR_TEACHER_ID,
            "question_version_id": QUESTION_VERSION_ID,
            "student_ids": list(STUDENT_IDS),
        }

    @app.get("/api/catalog/{question_version_id}")
    def catalog_get(question_version_id: str, request: Request) -> JSONResponse:
        snapshot = wired.approvals.read_snapshot(question_version_id)
        if snapshot is None:
            return _error(request.state.request_id, Err("not_found", "the question version does not exist"))
        return JSONResponse(_snapshot_body(snapshot))

    @app.post("/api/catalog/{question_version_id}/publish")
    def catalog_publish(question_version_id: str, request: Request) -> JSONResponse:
        result = publish_version(
            question_version_id,
            wired.approvals,
            wired.logger,
            request.state.request_id,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        return JSONResponse(_snapshot_body(result.value))

    @app.post("/api/catalog/{question_version_id}/revise")
    def catalog_revise(question_version_id: str, body: ReviseBody, request: Request) -> JSONResponse:
        result = revise_text(
            question_version_id,
            body.stem,
            body.answer_text,
            wired.approvals,
            wired.logger,
            request.state.request_id,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        return JSONResponse(_snapshot_body(result.value))

    @app.post("/api/catalog/{question_version_id}/retire")
    def catalog_retire(question_version_id: str, request: Request) -> JSONResponse:
        result = retire_version(
            question_version_id,
            wired.approvals,
            wired.logger,
            request.state.request_id,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        return JSONResponse(_snapshot_body(result.value))

    @app.get("/api/practice/papers")
    def papers() -> dict[str, object]:
        rows = visible_papers(ACTOR_TEACHER_ID, wired.auth, wired.practice)
        return {"count": len(rows), "papers": [_paper_body(row) for row in rows]}

    @app.get("/api/practice/confirmations/count")
    def confirmation_count() -> dict[str, int]:
        return {"count": visible_confirmation_count(ACTOR_TEACHER_ID, wired.auth, wired.practice)}

    @app.post("/api/practice/papers")
    def issue(body: IssueBody, request: Request) -> JSONResponse:
        result = open_paper(
            IssuePaperCommand(
                teacher_id=body.teacher_id,
                student_id=body.student_id,
                subject_id=body.subject_id,
                question_version_id=body.question_version_id,
                review_version_id=body.review_version_id,
            ),
            wired.approvals,
            wired.auth,
            wired.practice,
            wired.files,
            wired.renderer,
            wired.logger,
            request.state.request_id,
            actor_teacher_id=ACTOR_TEACHER_ID,
            attempt_text=synthetic_attempt_text(),
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        opened = result.value
        return JSONResponse(
            _paper_body(
                opened.paper,
                opened.fixture_answer_id,
                opened.render_code,
                opened.render_message,
            )
        )

    @app.post("/api/practice/papers/{paper_id}/handout")
    def handout(paper_id: str, request: Request) -> JSONResponse:
        result = hand_out_paper(
            paper_id,
            wired.approvals,
            wired.auth,
            wired.practice,
            wired.logger,
            request.state.request_id,
            actor_teacher_id=ACTOR_TEACHER_ID,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        return JSONResponse(_paper_body(result.value))

    @app.get("/api/practice/papers/{paper_id}/attempt")
    def attempt(paper_id: str, request: Request) -> JSONResponse:
        result = read_attempt(
            paper_id,
            wired.auth,
            wired.practice,
            wired.logger,
            request.state.request_id,
            actor_teacher_id=ACTOR_TEACHER_ID,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        view = result.value
        return JSONResponse(
            {
                "fixture_answer_id": view.fixture_answer_id,
                "paper_id": view.paper_id,
                "sub_question_id": view.sub_question_id,
                "review_version_id": view.review_version_id,
                "status": view.status,
                "answer_text": view.answer_text,
            }
        )

    @app.get("/api/practice/files/{file_id}")
    def file_bytes(file_id: str, request: Request) -> Response:
        result = read_file(
            file_id,
            wired.auth,
            wired.practice,
            wired.files,
            wired.logger,
            request.state.request_id,
            actor_teacher_id=ACTOR_TEACHER_ID,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        return Response(content=result.value, media_type="application/pdf")

    @app.post("/api/practice/confirmations")
    def confirm(body: ConfirmBody, request: Request) -> JSONResponse:
        result = confirm_attempt(
            ConfirmCommand(
                operation_key=body.operation_key,
                paper_id=body.paper_id,
                sub_question_id=body.sub_question_id,
                teacher_id=body.teacher_id,
                review_version_id=body.review_version_id,
                decision=body.decision,
                fixture_answer_id=body.fixture_answer_id,
            ),
            wired.auth,
            wired.practice,
            wired.logger,
            request.state.request_id,
            actor_teacher_id=ACTOR_TEACHER_ID,
        )
        if isinstance(result, Err):
            return _error(request.state.request_id, result)
        record = result.value
        return JSONResponse(
            {
                "confirmation_id": record.confirmation_id,
                "paper_id": record.paper_id,
                "sub_question_id": record.sub_question_id,
                "decision": record.decision,
                "count": visible_confirmation_count(ACTOR_TEACHER_ID, wired.auth, wired.practice),
            }
        )

    if _WEB.is_dir():
        app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")
    return app


def _request_id(header: str | None) -> str:
    if header and _REQUEST_ID.fullmatch(header):
        return header
    return uuid.uuid4().hex


def _error(request_id: str, err: Err, status: int = 409) -> JSONResponse:
    """Import and issue failures use code, message, and request_id. The review page does too."""
    return JSONResponse(
        status_code=status,
        content={"code": err.code, "message": err.message, "request_id": request_id},
    )


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


def _paper_body(
    paper: Paper,
    fixture_answer_id: str | None = None,
    render_code: str | None = None,
    render_message: str = "",
) -> dict[str, object]:
    return {
        "paper_id": paper.paper_id,
        "status": paper.status,
        "student_id": paper.student_id,
        "subject_id": paper.subject_id,
        "teacher_id": paper.teacher_id,
        "question_version_id": paper.question_version_id,
        "answer_version_id": paper.answer_version_id,
        "review_version_id": paper.review_version_id,
        "file_id": paper.file_id,
        "file_checksum": paper.file_checksum,
        "item_order": list(paper.item_order),
        "asset_ids": list(paper.asset_ids),
        "layout_template_id": paper.layout_template_id,
        "fixture_answer_id": fixture_answer_id,
        "render_code": render_code,
        "render_message": render_message,
    }


app = create_app()
