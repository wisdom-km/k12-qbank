"""Start a run, score what the machine can, and ask the model for the rest."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from backend.ai.domain.grade import grade_local
from backend.ai.domain.model import ModelFault, VisionModel
from backend.ai.domain.payload import judge_document, match_external, match_page, relative_box, transcribe_document
from backend.ai.domain.prompts import prompt_version
from backend.ai.domain.records import Context, JudgeAsk, Run, Suggestion, TranscribeAsk, WorkItem
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok, StoreFault
from backend.kernel.use_log import emit

_MODULE = "ai"
_ROLES = frozenset({"admin", "teacher"})


def start_run(
    *,
    intake_id: str,
    actor_id: str,
    actor_role: str,
    stores: object,
    runs: object,
    logger: Logger,
    request_id: str,
) -> Ok[str] | Err:
    started = time.perf_counter()
    if actor_role not in _ROLES:
        return _refuse(logger, request_id, started, "permission_denied")
    page = getattr(stores, "intake").get(intake_id)
    if page is None:
        return _refuse(logger, request_id, started, "not_found")
    paper = getattr(stores, "practice").get_paper(page.paper_id)
    if paper is None or not _allows(actor_role, actor_id, paper):
        return _refuse(logger, request_id, started, "permission_denied")
    if page.archived_at:
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module=_MODULE,
            outcome="intake_archived",
            started=started,
        )
        return Err("intake_archived", "收卷照片已到期归档")
    limit = _daily_limit()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if runs.count_started_on(day) >= limit:
        return _refuse(logger, request_id, started, "ai_daily_limit")
    provider = _provider()
    model_name = "mock" if provider == "mock" else _env("K12_AI_MODEL")
    run = Run(
        run_id="run-" + uuid.uuid4().hex,
        intake_id=intake_id,
        provider=provider,
        model=model_name,
        prompt_version=prompt_version(),
        status="queued",
        started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    try:
        runs.insert(run)
    except StoreFault as fault:
        return _refuse(logger, request_id, started, fault.code)
    _audit(
        logger,
        request_id,
        started,
        "ai_run_started",
        actor_id,
        actor_role,
        run.run_id,
        provider,
        model_name,
        "queued",
        0,
        0,
    )
    return Ok(run.run_id)


def read_run(
    *,
    run_id: str,
    actor_id: str,
    actor_role: str,
    stores: object,
    runs: object,
    logger: Logger,
    request_id: str,
) -> Ok[dict[str, object]] | Err:
    started = time.perf_counter()
    if actor_role not in _ROLES:
        return _refuse(logger, request_id, started, "permission_denied")
    run = runs.get(run_id)
    if run is None:
        return _refuse(logger, request_id, started, "not_found")
    page = getattr(stores, "intake").get(run.intake_id)
    paper = None if page is None else getattr(stores, "practice").get_paper(page.paper_id)
    if paper is None or not _allows(actor_role, actor_id, paper):
        return _refuse(logger, request_id, started, "permission_denied")
    return Ok(run_body(run))


def perform(
    context: Context,
    model: VisionModel,
    runs: object,
    logger: Logger,
    request_id: str,
    actor_id: str = "",
    actor_role: str = "",
) -> None:
    started = time.perf_counter()
    asks = tuple(_ask(item) for item in context.items)
    try:
        transcribed = model.transcribe(context.image, asks)
    except ModelFault as fault:
        _fail(context, runs, logger, request_id, actor_id, actor_role, fault.code, started, 0, 0)
        return
    except Exception:
        _fail(context, runs, logger, request_id, actor_id, actor_role, "failed", started, 0, 0)
        return
    by_order = {row.order_no: row for row in transcribed.items}
    if set(by_order) != {item.order_no for item in context.items}:
        _fail(context, runs, logger, request_id, actor_id, actor_role, "model_output_invalid", started, 0, 0)
        return
    external_match = match_external(context.expected_external_id, transcribed.seen_external_id)
    page_match = match_page(context.page_no, transcribed.seen_page_no)
    input_tokens = transcribed.input_tokens
    output_tokens = transcribed.output_tokens
    pending: list[JudgeAsk] = []
    local: dict[int, Suggestion] = {}
    for item in context.items:
        row = by_order[item.order_no]
        graded = grade_local(item.question_type, item.standard_answer, row.transcription, row.unreadable, item.blank_count)
        if graded is None:
            pending.append(
                JudgeAsk(
                    order_no=item.order_no,
                    question_type=item.question_type,
                    stem=item.stem,
                    standard_answer=item.standard_answer,
                    transcription=row.transcription,
                )
            )
            continue
        local[item.order_no] = _suggestion(context, row.order_no, row.transcription, row.unreadable, row.confidence, graded.verdict, graded.reason, "local")
    judged: dict[int, object] = {}
    if pending:
        try:
            result = model.judge(tuple(pending))
        except ModelFault as fault:
            _fail(context, runs, logger, request_id, actor_id, actor_role, fault.code, started, input_tokens, output_tokens)
            return
        except Exception:
            _fail(context, runs, logger, request_id, actor_id, actor_role, "failed", started, input_tokens, output_tokens)
            return
        input_tokens += result.input_tokens
        output_tokens += result.output_tokens
        judged = {item.order_no: item for item in result.items}
        if set(judged) != {item.order_no for item in pending}:
            _fail(context, runs, logger, request_id, actor_id, actor_role, "model_output_invalid", started, input_tokens, output_tokens)
            return
    suggestions: list[Suggestion] = []
    for item in context.items:
        row = by_order[item.order_no]
        found = judged.get(item.order_no)
        if found is None:
            suggestions.append(local[item.order_no])
            continue
        suggestions.append(
            _suggestion(
                context,
                item.order_no,
                row.transcription,
                row.unreadable,
                row.confidence,
                str(getattr(found, "verdict")),
                str(getattr(found, "reason")),
                "model",
            )
        )
    _save(
        context,
        runs,
        logger,
        request_id,
        actor_id,
        actor_role,
        "succeeded",
        "",
        started,
        input_tokens,
        output_tokens,
        external_match,
        page_match,
        tuple(suggestions),
    )


def recover_open_runs(runs: object) -> int:
    return int(runs.interrupt_open())


def run_body(run: Run) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "status": run.status,
        "error_code": run.error_code,
        "external_match": run.external_match or None,
        "page_match": run.page_match or None,
        "suggestions": [
            {
                "order_no": item.order_no,
                "transcription": item.transcription,
                "unreadable": item.unreadable,
                "confidence": item.confidence,
                "verdict": item.verdict,
                "reason": item.reason,
                "judged_by": item.judged_by,
            }
            for item in run.suggestions
        ],
    }


def captured_transcribe(items: tuple[TranscribeAsk, ...]) -> dict[str, object]:
    return transcribe_document(items)


def captured_judge(items: tuple[JudgeAsk, ...]) -> dict[str, object]:
    return judge_document(items)


def _ask(item: WorkItem) -> TranscribeAsk:
    return TranscribeAsk(
        order_no=item.order_no,
        question_type=item.question_type,
        boxes=tuple(relative_box(x, y, w, h) for x, y, w, h in item.boxes),
    )


def _suggestion(
    context: Context,
    order_no: int,
    transcription: str,
    unreadable: bool,
    confidence: float,
    verdict: str,
    reason: str,
    judged_by: str,
) -> Suggestion:
    return Suggestion(
        run_id=context.run_id,
        paper_id=context.paper_id,
        order_no=order_no,
        transcription=transcription,
        unreadable=unreadable,
        confidence=confidence,
        verdict=verdict,
        reason=reason,
        judged_by=judged_by,
    )


def _fail(
    context: Context,
    runs: object,
    logger: Logger,
    request_id: str,
    actor_id: str,
    actor_role: str,
    code: str,
    started: float,
    input_tokens: int,
    output_tokens: int,
) -> None:
    _save(
        context,
        runs,
        logger,
        request_id,
        actor_id,
        actor_role,
        "failed",
        code,
        started,
        input_tokens,
        output_tokens,
        "",
        "",
        (),
    )


def _save(
    context: Context,
    runs: object,
    logger: Logger,
    request_id: str,
    actor_id: str,
    actor_role: str,
    status: str,
    error_code: str,
    started: float,
    input_tokens: int,
    output_tokens: int,
    external_match: str,
    page_match: str,
    suggestions: tuple[Suggestion, ...],
) -> None:
    try:
        runs.finish(
            context.run_id,
            status=status,
            error_code=error_code,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            external_match=external_match,
            page_match=page_match,
            suggestions=suggestions,
        )
    except Exception:
        emit(
            logger,
            level="ERROR",
            event="use_case_failed",
            request_id=request_id,
            module=_MODULE,
            outcome="store_failed",
            started=started,
        )
        return
    if status == "failed":
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module=_MODULE,
            outcome=error_code or "failed",
            started=started,
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    _audit(
        logger,
        request_id,
        started,
        "ai_run_finished",
        actor_id,
        actor_role,
        context.run_id,
        context.provider,
        context.model_name,
        status,
        input_tokens,
        output_tokens,
        elapsed,
    )


def _audit(
    logger: Logger,
    request_id: str,
    started: float,
    event: str,
    actor_id: str,
    actor_role: str,
    run_id: str,
    provider: str,
    model_name: str,
    status: str,
    input_tokens: int,
    output_tokens: int,
    elapsed: int = 0,
) -> None:
    detail = json.dumps(
        {
            "run_id": run_id,
            "provider": provider,
            "model": model_name,
            "status": status,
            "duration_ms": elapsed,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    emit(
        logger,
        level="INFO",
        event=event,
        request_id=request_id,
        module=_MODULE,
        outcome="ok" if status != "failed" else "err",
        started=started,
        actor_user_id=actor_id,
        target_kind="ai_run",
        target_id=run_id,
        audit=True,
        detail=detail,
        action=event,
        actor_role=actor_role,
    )


def _allows(actor_role: str, actor_id: str, paper: object) -> bool:
    if actor_role == "admin":
        return True
    return actor_role == "teacher" and str(getattr(paper, "teacher_id", "")) == actor_id


def _refuse(logger: Logger, request_id: str, started: float, code: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module=_MODULE,
        outcome=code,
        started=started,
    )
    return Err(code, code)


def _provider() -> str:
    return _env("K12_AI_PROVIDER") or "mock"


def _daily_limit() -> int:
    raw = _env("K12_AI_DAILY_LIMIT")
    if not raw:
        return 500
    try:
        value = int(raw)
    except ValueError:
        return 500
    if value < 0:
        return 500
    return value


def _env(name: str) -> str:
    import os

    return os.environ.get(name, "").strip()
