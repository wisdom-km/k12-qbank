"""Recognition HTTP. The page does not choose the teacher, and it does not adopt a suggestion."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.ai.application.accuracy import accuracy_report
from backend.ai.application.load import load_context
from backend.ai.application.recognize import perform, read_run, start_run
from backend.bootstrap.http_errors import error_response
from backend.bootstrap.schemas.accuracy import AccuracyResponse
from backend.identity.application.guard import admin_only
from backend.kernel.result import Err
from backend.kernel.use_log import emit

_MODULE = "ai"


class _Pool(ThreadPoolExecutor):
    """At most two recognition jobs. The threads do not keep the process alive."""

    def _adjust_thread_count(self) -> None:
        original = threading.Thread

        class _Daemon(original):  # type: ignore[type-arg, misc]
            def __init__(self, *args: object, **kwargs: object) -> None:
                kwargs["daemon"] = True
                super().__init__(*args, **kwargs)  # type: ignore[arg-type]

        threading.Thread = _Daemon  # type: ignore[misc]
        try:
            super()._adjust_thread_count()
        finally:
            threading.Thread = original


def register_ai(app: FastAPI) -> None:
    app.state.ai_pool = _Pool(max_workers=2, thread_name_prefix="k12-ai")

    @app.post("/api/practice/intake/{intake_id}/ai-runs", status_code=202)
    def start_ai_run(intake_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        actor = request.state.actor
        result = start_run(
            intake_id=intake_id,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            stores=loop,
            runs=loop.ai_runs,
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        request.app.state.ai_pool.submit(
            _execute,
            request.app,
            result.value,
            request.state.request_id,
            str(actor.user_id),
            str(actor.role),
        )
        return JSONResponse(status_code=202, content={"run_id": result.value, "status": "queued"})

    @app.get("/api/practice/ai-runs/{run_id}")
    def read_ai_run(run_id: str, request: Request) -> JSONResponse:
        loop = request.app.state.loop
        actor = request.state.actor
        result = read_run(
            run_id=run_id,
            actor_id=str(actor.user_id),
            actor_role=str(actor.role),
            stores=loop,
            runs=loop.ai_runs,
            logger=loop.logger,
            request_id=request.state.request_id,
        )
        if isinstance(result, Err):
            return error_response(request.state.request_id, result)
        return JSONResponse(result.value)

    @app.get("/api/admin/ai/accuracy", response_model=AccuracyResponse)
    def ai_accuracy(request: Request, provider: str = "", model: str = "") -> JSONResponse:
        refused = admin_only(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        loop = request.app.state.loop
        body = AccuracyResponse.model_validate(
            accuracy_report(loop.ai_runs, loop.decisions, provider=provider, model=model)
        )
        return JSONResponse(body.model_dump())


def _execute(app: FastAPI, run_id: str, request_id: str, actor_id: str, actor_role: str) -> None:
    loop = app.state.loop
    started = time.perf_counter()
    try:
        if not loop.ai_runs.mark_running(run_id):
            return
        run = loop.ai_runs.get(run_id)
        context = None if run is None else load_context(loop, run)
        if context is None:
            _cannot_load(loop, run_id, request_id, started)
            return
        perform(
            context,
            loop.model,
            loop.ai_runs,
            loop.logger,
            request_id,
            actor_id,
            actor_role,
        )
    except Exception:
        emit(
            loop.logger,
            level="ERROR",
            event="use_case_failed",
            request_id=request_id,
            module=_MODULE,
            outcome="store_failed",
            started=started,
        )
        _cannot_load(loop, run_id, request_id, started)


def _cannot_load(loop: object, run_id: str, request_id: str, started: float) -> None:
    try:
        loop.ai_runs.finish(  # type: ignore[attr-defined]
            run_id,
            status="failed",
            error_code="failed",
            input_tokens=0,
            output_tokens=0,
            external_match="",
            page_match="",
            suggestions=(),
        )
    except Exception:
        emit(
            loop.logger,  # type: ignore[attr-defined]
            level="ERROR",
            event="use_case_failed",
            request_id=request_id,
            module=_MODULE,
            outcome="store_failed",
            started=started,
        )
        return
    emit(
        loop.logger,  # type: ignore[attr-defined]
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module=_MODULE,
        outcome="failed",
        started=started,
    )
