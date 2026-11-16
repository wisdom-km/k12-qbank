"""Issue one student paper. R1 refusal happens here, before any write."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from backend.catalog.api import ApprovalPort, issuable_snapshot
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import IssuePaperCommand
from backend.practice.application.ports import Authorizer, PracticeStore
from backend.practice.domain.paper import Paper, freeze_paper


def issue_paper(
    command: IssuePaperCommand,
    approvals: ApprovalPort,
    auth: Authorizer,
    store: PracticeStore,
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
    *,
    actor_teacher_id: str,
) -> Ok[Paper] | Err:
    started = time.perf_counter()
    identify = new_id or (lambda: uuid.uuid4().hex)
    loaded = read_store(
        lambda: approvals.read_snapshot(command.question_version_id),
        logger,
        request_id,
        "practice.issue",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    ready = issuable_snapshot(loaded.value)
    if isinstance(ready, Err):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="practice.issue",
            outcome=ready.code,
            started=started,
        )
        return ready
    if command.subject_id != ready.subject_id:
        return _refuse_issue(
            logger,
            request_id,
            started,
            "subject_mismatch",
            "the requested subject does not match the catalog record",
        )
    if command.teacher_id != actor_teacher_id or not auth.allow(
        actor_teacher_id, command.student_id, ready.subject_id
    ):
        return _refuse_issue(
            logger,
            request_id,
            started,
            "unauthorized",
            "this teacher cannot issue for that student and subject",
        )
    paper = freeze_paper(
        paper_id=identify(),
        teacher_id=actor_teacher_id,
        student_id=command.student_id,
        subject_id=ready.subject_id,
        question_version_id=ready.question_version_id,
        answer_version_id=ready.answer_version_id,
        asset_ids=ready.asset_ids,
        layout_template_id=ready.layout_template_id,
        review_version_id=command.review_version_id,
        item_order=ready.item_order,
    )
    if isinstance(paper, Err):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="practice.issue",
            outcome=paper.code,
            started=started,
        )
        return paper
    saved = read_store(
        lambda: store.add_paper(paper),
        logger,
        request_id,
        "practice.issue",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="paper_created",
        request_id=request_id,
        module="practice.issue",
        outcome=paper.paper_id,
        started=started,
    )
    return Ok(paper)


def _refuse_issue(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module="practice.issue",
        outcome=code,
        started=started,
    )
    return Err(code, message)
