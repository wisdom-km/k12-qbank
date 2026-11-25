"""Teacher conclusions. The session user is the teacher. The body does not name one."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.ai.application.current import recognition_of
from backend.bootstrap.http_errors import error_response
from backend.kernel.result import Err
from backend.practice.application.decide import adopt_confident, review_paper, save_decision


class DecisionBody(BaseModel):
    action: str
    verdict: str = ""
    corrected_transcription: str = ""
    comment: str = ""


def register_decision(app: FastAPI) -> None:
    @app.get("/api/practice/papers/{paper_id}/review")
    def review(paper_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        actor = request.state.actor
        result = review_paper(
            paper_id=paper_id,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            store=loop.practice,
            items=loop.items,
            approvals=loop.approvals,
            decisions=loop.decisions,
            facts=recognition_of(loop, paper_id),
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        return JSONResponse(result.value)

    @app.put("/api/practice/papers/{paper_id}/items/{order_no}/decision")
    def decide(paper_id: str, order_no: int, body: DecisionBody, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        actor = request.state.actor
        result = save_decision(
            paper_id=paper_id,
            order_no=order_no,
            action=body.action,
            verdict=body.verdict,
            corrected_transcription=body.corrected_transcription,
            comment=body.comment,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            store=loop.practice,
            items=loop.items,
            decisions=loop.decisions,
            facts=recognition_of(loop, paper_id),
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        return JSONResponse(result.value)

    @app.post("/api/practice/papers/{paper_id}/decisions/adopt-confident")
    def adopt_ready(paper_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        actor = request.state.actor
        result = adopt_confident(
            paper_id=paper_id,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            store=loop.practice,
            items=loop.items,
            decisions=loop.decisions,
            facts=recognition_of(loop, paper_id),
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        return JSONResponse(result.value)
