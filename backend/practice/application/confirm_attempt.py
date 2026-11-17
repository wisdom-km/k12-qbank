"""Confirm one fixture answer. R3 and R5 are decided here, not in a page."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import ConfirmCommand
from backend.practice.application.ports import Authorizer, PracticeStore
from backend.practice.domain.confirm import Confirmation, parse_decision, parse_operation_key


def confirm_attempt(
    command: ConfirmCommand,
    auth: Authorizer,
    store: PracticeStore,
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
    *,
    actor_teacher_id: str,
) -> Ok[Confirmation] | Err:
    started = time.perf_counter()
    identify = new_id or (lambda: uuid.uuid4().hex)
    parsed = parse_operation_key(command.operation_key)
    if isinstance(parsed, Err):
        return _refuse(logger, request_id, started, parsed.code, parsed.message)
    loaded = read_store(
        lambda: store.get_paper(command.paper_id),
        logger,
        request_id,
        "practice.confirm",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    if paper is None:
        return _refuse(logger, request_id, started, "not_found", "the student paper does not exist")
    if command.teacher_id != actor_teacher_id or not auth.allow(
        actor_teacher_id, paper.student_id, paper.subject_id
    ):
        return _refuse(
            logger,
            request_id,
            started,
            "unauthorized",
            "this teacher cannot confirm for that student and subject",
        )
    decision = parse_decision(command.decision)
    if isinstance(decision, Err):
        return _refuse(logger, request_id, started, decision.code, decision.message)
    record = Confirmation(
        confirmation_id=identify(),
        operation_key=parsed,
        paper_id=command.paper_id,
        sub_question_id=command.sub_question_id,
        teacher_id=actor_teacher_id,
        review_version_id=command.review_version_id,
        decision=decision,
        fixture_answer_id=command.fixture_answer_id,
    )
    saved = read_store(
        lambda: store.commit_confirmation(record),
        logger,
        request_id,
        "practice.confirm",
        started,
    )
    if isinstance(saved, Err):
        return saved
    placed = saved.value
    if isinstance(placed, Err):
        return _refuse(logger, request_id, started, placed.code, placed.message)
    emit(
        logger,
        level="INFO",
        event="attempt_confirmed",
        request_id=request_id,
        module="practice.confirm",
        outcome=placed.confirmation_id,
        started=started,
    )
    return Ok(placed)


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module="practice.confirm",
        outcome=code,
        started=started,
    )
    return Err(code, message)
