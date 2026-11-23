"""Issue one student paper. R1 refusal happens here, before any write."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from backend.catalog.api import ApprovalPort, Publications, issuable_snapshot
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import IssuePaperCommand
from backend.practice.application.ports import Authorizer, PracticeStore
from backend.practice.domain.page_face import formula_from_stem
from backend.practice.domain.paper import Paper, freeze_paper


@dataclass(frozen=True)
class PreparedIssue:
    """A paper and the answer text copied before any store write."""

    paper: Paper
    answer_text: str
    stem: str = ""


def prepare_issue(
    command: IssuePaperCommand,
    approvals: ApprovalPort,
    auth: Authorizer,
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
    *,
    actor_teacher_id: str,
    require_item_order: bool = False,
) -> Ok[PreparedIssue] | Err:
    """Check the catalog, the subject, and the teacher. Do not store a paper."""
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
    snapshot = loaded.value
    ready = issuable_snapshot(snapshot)
    if isinstance(ready, Err):
        return _refuse_issue(logger, request_id, started, ready.code, ready.message)
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
    if require_item_order and not ready.item_order:
        return _refuse_issue(logger, request_id, started, "not_frozen", "the paper has no item order")
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
        formula=formula_from_stem(snapshot.stem if snapshot is not None else ""),
        qr_printed=command.qr_printed,
        printed_external_id=command.printed_external_id,
    )
    if isinstance(paper, Err):
        return _refuse_issue(logger, request_id, started, paper.code, paper.message)
    answer_text = snapshot.answer_text if snapshot is not None else ""
    stem = snapshot.stem if snapshot is not None else ""
    return Ok(PreparedIssue(paper=paper, answer_text=answer_text, stem=stem))


def gate_active_publication(
    publications: Publications,
    paper: Paper,
    logger: Logger,
    request_id: str,
) -> Err | None:
    """Refuse when this binding has no active publication. Callers must pass a ledger."""
    if publications.active_of(paper.question_version_id, paper.answer_version_id) is not None:
        return None
    return _refuse_issue(
        logger,
        request_id,
        time.perf_counter(),
        "no_active_publication",
        "the question version and the answer version have no active publication",
    )


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
    publications: Publications,
) -> Ok[Paper] | Err:
    prepared = prepare_issue(
        command,
        approvals,
        auth,
        logger,
        request_id,
        new_id,
        actor_teacher_id=actor_teacher_id,
    )
    if isinstance(prepared, Err):
        return prepared
    paper = prepared.value.paper
    blocked = gate_active_publication(publications, paper, logger, request_id)
    if blocked is not None:
        return blocked
    started = time.perf_counter()
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
