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
from backend.practice.domain.confirm import Confirmation, classify_operation, parse_operation_key


def confirm_attempt(
    command: ConfirmCommand,
    auth: Authorizer,
    store: PracticeStore,
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
) -> Ok[Confirmation] | Err:
    started = time.perf_counter()
    identify = new_id or (lambda: uuid.uuid4().hex)
    parsed = parse_operation_key(command.operation_key)
    if isinstance(parsed, Err):
        return _refuse(logger, request_id, started, parsed.code, parsed.message)
    operation_key = parsed.value
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
    if not auth.allow(command.teacher_id, paper.student_id, paper.subject_id):
        return _refuse(
            logger,
            request_id,
            started,
            "unauthorized",
            "this teacher cannot confirm for that student and subject",
        )
    found = read_store(
        lambda: store.get_confirmation(operation_key),
        logger,
        request_id,
        "practice.confirm",
        started,
    )
    if isinstance(found, Err):
        return found
    existing = found.value
    kind = classify_operation(
        existing,
        operation_key=operation_key,
        paper_id=command.paper_id,
        sub_question_id=command.sub_question_id,
        teacher_id=command.teacher_id,
        review_version_id=command.review_version_id,
        decision=command.decision,
        fixture_answer_id=command.fixture_answer_id,
    )
    if kind == "replay" and existing is not None:
        emit(
            logger,
            level="INFO",
            event="attempt_confirmed",
            request_id=request_id,
            module="practice.confirm",
            outcome=existing.confirmation_id,
            started=started,
        )
        return Ok(existing)
    if kind == "mismatch":
        return _refuse(
            logger,
            request_id,
            started,
            "key_content_mismatch",
            "the same operation key was sent with different content",
        )
    if command.review_version_id != paper.review_version_id:
        return _refuse(
            logger,
            request_id,
            started,
            "version_mismatch",
            "the review version changed",
        )
    slot = read_store(
        lambda: store.find_slot(command.paper_id, command.sub_question_id, command.review_version_id),
        logger,
        request_id,
        "practice.confirm",
        started,
    )
    if isinstance(slot, Err):
        return slot
    if slot.value is not None:
        return _refuse(
            logger,
            request_id,
            started,
            "confirm_conflict",
            "another confirmation already holds this review version",
        )
    record = Confirmation(
        confirmation_id=identify(),
        operation_key=operation_key,
        paper_id=command.paper_id,
        sub_question_id=command.sub_question_id,
        teacher_id=command.teacher_id,
        review_version_id=command.review_version_id,
        decision=command.decision,
        fixture_answer_id=command.fixture_answer_id,
    )
    saved = read_store(
        lambda: store.add_confirmation(record),
        logger,
        request_id,
        "practice.confirm",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="attempt_confirmed",
        request_id=request_id,
        module="practice.confirm",
        outcome=record.confirmation_id,
        started=started,
    )
    return Ok(record)


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
