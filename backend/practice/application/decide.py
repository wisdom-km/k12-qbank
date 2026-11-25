"""Save a teacher conclusion. A suggestion stays a suggestion until this runs."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from backend.catalog.api import ApprovalPort
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.application.ports import PracticeItems, PracticeStore
from backend.practice.domain.decision import (
    PlannedDecision,
    SuggestionFact,
    TeacherDecision,
    confident_local,
    needs_review,
    plan_decision,
    review_threshold,
    same_decision,
)

_MODULE = "practice.decide"
_ROLES = frozenset({"admin", "teacher"})


def review_paper(
    *,
    paper_id: str,
    actor_id: str,
    actor_role: str,
    store: PracticeStore,
    items: PracticeItems,
    approvals: ApprovalPort,
    decisions: object,
    facts: dict[str, object],
    logger: Logger,
    request_id: str,
) -> Ok[dict[str, object]] | Err:
    started = time.perf_counter()
    allowed = _paper(store, paper_id, actor_id, actor_role, logger, request_id, started)
    if isinstance(allowed, Err):
        return allowed
    threshold = _threshold()
    by_suggestion = {_fact(row) for row in _rows(facts, "suggestions")}
    suggestions = {fact.order_no: fact for fact in by_suggestion}
    stale = set(_numbers(facts, "stale_orders"))
    received = set(_numbers(facts, "received_pages"))
    current = {row.order_no: row for row in decisions.currents(paper_id)}  # type: ignore[attr-defined]
    body_items: list[dict[str, object]] = []
    for item in sorted(items.items_of(paper_id), key=lambda row: row.order_no):
        snapshot = approvals.read_snapshot(item.question_version_id)
        fact = suggestions.get(item.order_no)
        decision = current.get(item.order_no)
        body_items.append(
            {
                "order_no": item.order_no,
                "question_type": "" if snapshot is None else str(getattr(snapshot, "type", "") or ""),
                "stem": item.stem_text,
                "standard_answer": item.answer_text,
                "page_no": item.page_no,
                "intake_status": "received" if item.page_no in received else "missing",
                "stale": fact is None and item.order_no in stale,
                "suggestion": None if fact is None else _suggestion_body(fact, threshold),
                "decision": None if decision is None else _decision_body(decision),
            }
        )
    confirmed = sum(1 for row in body_items if row["decision"] is not None)
    correct = sum(
        1
        for row in body_items
        if isinstance(row["decision"], dict) and row["decision"].get("verdict") == "correct"
    )
    total = len(body_items)
    return Ok(
        {
            "paper_id": paper_id,
            "threshold": threshold,
            "confirmed": confirmed,
            "total": total,
            "correct": correct,
            "done": total > 0 and confirmed == total,
            "mismatch_pages": _numbers(facts, "mismatch_pages"),
            "items": body_items,
        }
    )


def save_decision(
    *,
    paper_id: str,
    order_no: int,
    action: str,
    verdict: str,
    corrected_transcription: str,
    comment: str,
    actor_id: str,
    actor_role: str,
    store: PracticeStore,
    items: PracticeItems,
    decisions: object,
    facts: dict[str, object],
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
) -> Ok[dict[str, object]] | Err:
    started = time.perf_counter()
    allowed = _paper(store, paper_id, actor_id, actor_role, logger, request_id, started)
    if isinstance(allowed, Err):
        return allowed
    if not any(item.order_no == order_no for item in items.items_of(paper_id)):
        return _refuse(logger, request_id, started, "not_found")
    fact = _suggestion_for(facts, order_no)
    planned = plan_decision(
        action,
        verdict,
        fact,
        stale=fact is None and order_no in set(_numbers(facts, "stale_orders")),
        corrected_transcription=corrected_transcription,
        comment=comment,
    )
    if isinstance(planned, Err):
        return _refuse(logger, request_id, started, planned.code)
    return _commit(
        paper_id,
        order_no,
        action,
        planned,
        actor_id,
        actor_role,
        decisions,
        logger,
        request_id,
        started,
        new_id or (lambda: uuid.uuid4().hex),
    )


def adopt_confident(
    *,
    paper_id: str,
    actor_id: str,
    actor_role: str,
    store: PracticeStore,
    items: PracticeItems,
    decisions: object,
    facts: dict[str, object],
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
) -> Ok[dict[str, object]] | Err:
    """Adopt the confident local rows. Items the teacher already decided stay."""
    started = time.perf_counter()
    allowed = _paper(store, paper_id, actor_id, actor_role, logger, request_id, started)
    if isinstance(allowed, Err):
        return allowed
    threshold = _threshold()
    identify = new_id or (lambda: uuid.uuid4().hex)
    taken: list[int] = []
    for item in sorted(items.items_of(paper_id), key=lambda row: row.order_no):
        fact = _suggestion_for(facts, item.order_no)
        if fact is None or not confident_local(fact, threshold):
            continue
        if decisions.current(paper_id, item.order_no) is not None:  # type: ignore[attr-defined]
            continue
        planned = plan_decision("adopt", "", fact, stale=False, corrected_transcription="", comment="")
        if isinstance(planned, Err):
            continue
        saved = _commit(
            paper_id,
            item.order_no,
            "adopt",
            planned,
            actor_id,
            actor_role,
            decisions,
            logger,
            request_id,
            started,
            identify,
        )
        if isinstance(saved, Err):
            return saved
        taken.append(item.order_no)
    return Ok({"paper_id": paper_id, "order_nos": taken, "threshold": threshold})


def _commit(
    paper_id: str,
    order_no: int,
    action: str,
    planned: PlannedDecision,
    actor_id: str,
    actor_role: str,
    decisions: object,
    logger: Logger,
    request_id: str,
    started: float,
    identify: Callable[[], str],
) -> Ok[dict[str, object]] | Err:
    existing = decisions.current(paper_id, order_no)  # type: ignore[attr-defined]
    if existing is not None and same_decision(
        source=existing.source,
        verdict=existing.verdict,
        ai_run_id=existing.ai_run_id,
        ai_verdict=existing.ai_verdict,
        ai_confidence=existing.ai_confidence,
        corrected_transcription=existing.corrected_transcription,
        comment=existing.comment,
        planned=planned,
    ):
        return Ok(_decision_body(existing))
    row = TeacherDecision(
        decision_id="decision-" + identify(),
        paper_id=paper_id,
        order_no=order_no,
        verdict=planned.verdict,
        source=planned.source,
        decided_by=actor_id,
        decided_at=_now(),
        ai_run_id=planned.ai_run_id,
        ai_verdict=planned.ai_verdict,
        ai_confidence=planned.ai_confidence,
        corrected_transcription=planned.corrected_transcription,
        comment=planned.comment,
    )
    saved = read_store(
        lambda: decisions.replace(row),  # type: ignore[attr-defined]
        logger,
        request_id,
        _MODULE,
        started,
    )
    if isinstance(saved, Err):
        return saved
    _audit(logger, request_id, started, actor_id, actor_role, row, action, planned.agrees)
    return Ok(_decision_body(row))


def _paper(
    store: PracticeStore,
    paper_id: str,
    actor_id: str,
    actor_role: str,
    logger: Logger,
    request_id: str,
    started: float,
) -> Ok[object] | Err:
    if actor_role not in _ROLES:
        return _refuse(logger, request_id, started, "permission_denied")
    loaded = read_store(
        lambda: store.get_paper(paper_id),
        logger,
        request_id,
        _MODULE,
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    if paper is None:
        return _refuse(logger, request_id, started, "not_found")
    if actor_role == "admin" or (actor_role == "teacher" and paper.teacher_id == actor_id):
        return Ok(paper)
    return _refuse(logger, request_id, started, "permission_denied")


def _suggestion_for(facts: dict[str, object], order_no: int) -> SuggestionFact | None:
    for row in _rows(facts, "suggestions"):
        if int(row["order_no"]) == order_no:
            return _fact(row)
    return None


def _fact(row: dict[str, object]) -> SuggestionFact:
    return SuggestionFact(
        run_id=str(row["run_id"]),
        order_no=int(row["order_no"]),  # type: ignore[arg-type]
        transcription=str(row["transcription"]),
        confidence=float(row["confidence"]),  # type: ignore[arg-type]
        verdict=str(row["verdict"]),
        reason=str(row["reason"]),
        judged_by=str(row["judged_by"]),
        unreadable=bool(row["unreadable"]),
    )


def _rows(facts: dict[str, object], name: str) -> list[dict[str, object]]:
    raw = facts.get(name) or []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _numbers(facts: dict[str, object], name: str) -> list[int]:
    raw = facts.get(name) or []
    if not isinstance(raw, list):
        return []
    return [int(item) for item in raw]


def _suggestion_body(fact: SuggestionFact, threshold: float) -> dict[str, object]:
    return {
        "run_id": fact.run_id,
        "transcription": fact.transcription,
        "confidence": fact.confidence,
        "verdict": fact.verdict,
        "reason": fact.reason,
        "judged_by": fact.judged_by,
        "unreadable": fact.unreadable,
        "needs_review": needs_review(fact.confidence, fact.unreadable, threshold),
    }


def _decision_body(row: TeacherDecision) -> dict[str, object]:
    return {
        "verdict": row.verdict,
        "source": row.source,
        "decided_at": row.decided_at,
        "corrected_transcription": row.corrected_transcription,
        "comment": row.comment,
        "ai_verdict": row.ai_verdict,
        "ai_confidence": row.ai_confidence,
        "agrees": row.source == "adopted" or (row.source == "revised" and row.verdict == row.ai_verdict),
    }


def _audit(
    logger: Logger,
    request_id: str,
    started: float,
    actor_id: str,
    actor_role: str,
    row: TeacherDecision,
    action: str,
    agrees: bool,
) -> None:
    detail = json.dumps(
        {
            "paper_id": row.paper_id,
            "order_no": row.order_no,
            "action": action,
            "verdict": row.verdict,
            "agrees": agrees,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    emit(
        logger,
        level="INFO",
        event="teacher_decision_saved",
        request_id=request_id,
        module=_MODULE,
        outcome="ok",
        started=started,
        actor_user_id=actor_id,
        target_kind="teacher_decision",
        target_id=row.decision_id,
        audit=True,
        detail=detail,
        action="teacher_decision_saved",
        actor_role=actor_role,
    )


def _threshold() -> float:
    return review_threshold(os.environ.get("K12_AI_REVIEW_THRESHOLD", ""))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
