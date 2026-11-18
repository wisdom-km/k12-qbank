"""Practice HTTP. The body teacher id is ignored. The actor is the session user."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from backend.bootstrap.http_errors import error_response
from backend.bootstrap.seed import synthetic_attempt_text
from backend.kernel.result import Err
from backend.practice.api import ConfirmCommand, IssuePaperCommand, Paper
from backend.practice.application.confirm_attempt import confirm_attempt
from backend.practice.application.open_paper import open_paper, read_attempt
from backend.practice.application.render_paper import hand_out_paper, read_file
from backend.practice.application.visible import visible_confirmation_count, visible_papers


class IssueBody(BaseModel):
    student_id: str
    subject_id: str
    question_version_id: str
    review_version_id: str
    teacher_id: str = ""


class ConfirmBody(BaseModel):
    operation_key: str
    paper_id: str
    sub_question_id: str
    review_version_id: str
    decision: str
    fixture_answer_id: str
    teacher_id: str = ""


def register_practice(app: FastAPI) -> None:
    @app.get("/api/practice/papers")
    def papers(request: Request) -> dict[str, object]:
        actor = _actor(request)
        rows = visible_papers(actor, request.app.state.loop.auth, request.app.state.loop.practice)
        return {"count": len(rows), "papers": [_paper_body(row) for row in rows]}

    @app.get("/api/practice/confirmations/count")
    def confirmation_count(request: Request) -> dict[str, int]:
        actor = _actor(request)
        count = visible_confirmation_count(actor, request.app.state.loop.auth, request.app.state.loop.practice)
        return {"count": count}

    @app.post("/api/practice/papers")
    def issue(body: IssueBody, request: Request) -> JSONResponse:
        return _issue(body, request)

    @app.post("/api/practice/papers/{paper_id}/handout")
    def handout(paper_id: str, request: Request) -> JSONResponse:
        return _handout(paper_id, request)

    @app.get("/api/practice/papers/{paper_id}/attempt")
    def attempt(paper_id: str, request: Request) -> JSONResponse:
        return _attempt(paper_id, request)

    @app.get("/api/practice/files/{file_id}")
    def file_bytes(file_id: str, request: Request) -> Response:
        return _file(file_id, request)

    @app.post("/api/practice/confirmations")
    def confirm(body: ConfirmBody, request: Request) -> JSONResponse:
        return _confirm(body, request)


def _issue(body: IssueBody, request: Request) -> JSONResponse:
    loop = request.app.state.loop
    actor = _actor(request)
    result = open_paper(
        IssuePaperCommand(
            teacher_id=actor,
            student_id=body.student_id,
            subject_id=body.subject_id,
            question_version_id=body.question_version_id,
            review_version_id=body.review_version_id,
        ),
        loop.approvals,
        loop.auth,
        loop.practice,
        loop.files,
        loop.renderer,
        loop.logger,
        request.state.request_id,
        actor_teacher_id=actor,
        attempt_text=synthetic_attempt_text(),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    opened = result.value
    return JSONResponse(_paper_body(opened.paper, opened.fixture_answer_id, opened.render_code, opened.render_message))


def _handout(paper_id: str, request: Request) -> JSONResponse:
    loop = request.app.state.loop
    actor = _actor(request)
    result = hand_out_paper(paper_id, loop.approvals, loop.auth, loop.practice, loop.logger, request.state.request_id, actor_teacher_id=actor)
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse(_paper_body(result.value))


def _attempt(paper_id: str, request: Request) -> JSONResponse:
    loop = request.app.state.loop
    actor = _actor(request)
    result = read_attempt(paper_id, loop.auth, loop.practice, loop.logger, request.state.request_id, actor_teacher_id=actor)
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
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


def _file(file_id: str, request: Request) -> Response:
    loop = request.app.state.loop
    actor = _actor(request)
    result = read_file(file_id, loop.auth, loop.practice, loop.files, loop.logger, request.state.request_id, actor_teacher_id=actor)
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return Response(content=result.value, media_type="application/pdf")


def _confirm(body: ConfirmBody, request: Request) -> JSONResponse:
    loop = request.app.state.loop
    actor = _actor(request)
    result = confirm_attempt(
        ConfirmCommand(
            operation_key=body.operation_key,
            paper_id=body.paper_id,
            sub_question_id=body.sub_question_id,
            teacher_id=actor,
            review_version_id=body.review_version_id,
            decision=body.decision,
            fixture_answer_id=body.fixture_answer_id,
        ),
        loop.auth,
        loop.practice,
        loop.logger,
        request.state.request_id,
        actor_teacher_id=actor,
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    record = result.value
    count = visible_confirmation_count(actor, loop.auth, loop.practice)
    return JSONResponse(
        {
            "confirmation_id": record.confirmation_id,
            "paper_id": record.paper_id,
            "sub_question_id": record.sub_question_id,
            "decision": record.decision,
            "count": count,
        }
    )


def _actor(request: Request) -> str:
    return str(request.state.actor.user_id)


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
