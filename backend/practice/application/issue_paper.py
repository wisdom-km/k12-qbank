"""Issue one student paper. R1 refusal happens here, before any write."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from backend.catalog.api import ApprovalPort, copy_issue_snapshot, issue_block
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
) -> Ok[Paper] | Err:
    started = time.perf_counter()
    identify = new_id or (lambda: uuid.uuid4().hex)
    if not auth.allow(command.teacher_id, command.student_id, command.subject_id):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="practice.issue",
            outcome="unauthorized",
            started=started,
        )
        return Err("unauthorized", "this teacher cannot issue for that student and subject")
    loaded = read_store(
        lambda: approvals.read_snapshot(command.question_version_id),
        logger,
        request_id,
        "practice.issue",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    blocked = issue_block(loaded.value)
    if blocked is not None:
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="practice.issue",
            outcome=blocked.code,
            started=started,
        )
        return blocked
    snapshot = loaded.value
    if snapshot is None:
        return Err("not_found", "the question version does not exist")
    frozen = copy_issue_snapshot(snapshot)
    if isinstance(frozen, Err):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="practice.issue",
            outcome=frozen.code,
            started=started,
        )
        return frozen
    paper = freeze_paper(
        paper_id=identify(),
        teacher_id=command.teacher_id,
        student_id=command.student_id,
        subject_id=command.subject_id,
        question_version_id=frozen.question_version_id,
        answer_version_id=frozen.answer_version_id,
        asset_ids=frozen.asset_ids,
        layout_template_id=frozen.layout_template_id,
        review_version_id=command.review_version_id,
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
