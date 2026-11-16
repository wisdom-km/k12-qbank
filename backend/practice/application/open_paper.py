"""Issue one paper and bind the synthetic attempt as one store write, then render."""

from __future__ import annotations

import time
from collections.abc import Callable

from backend.catalog.api import ApprovalPort
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import AttemptView, IssuePaperCommand, OpenedPaper
from backend.practice.application.issue_paper import prepare_issue
from backend.practice.application.ports import Authorizer, FileStore, PageRenderer, PracticeStore
from backend.practice.application.render_paper import render_paper
from backend.practice.domain.confirm import PendingAnswer


def open_paper(
    command: IssuePaperCommand,
    approvals: ApprovalPort,
    auth: Authorizer,
    store: PracticeStore,
    files: FileStore,
    renderer: PageRenderer,
    logger: Logger,
    request_id: str,
    new_id: Callable[[], str] | None = None,
    *,
    actor_teacher_id: str,
) -> Ok[OpenedPaper] | Err:
    prepared = prepare_issue(
        command,
        approvals,
        auth,
        logger,
        request_id,
        new_id,
        actor_teacher_id=actor_teacher_id,
        require_item_order=True,
    )
    if isinstance(prepared, Err):
        return prepared
    paper = prepared.value.paper
    attempt_id = "fixture-answer-" + paper.paper_id
    answer = PendingAnswer(
        fixture_answer_id=attempt_id,
        paper_id=paper.paper_id,
        sub_question_id=paper.item_order[0],
        review_version_id=paper.review_version_id,
        student_id=paper.student_id,
        status="pending",
        answer_text=prepared.value.answer_text,
    )
    started = time.perf_counter()
    saved = read_store(
        lambda: store.place_issued(paper, answer),
        logger,
        request_id,
        "practice.bind",
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
    emit(
        logger,
        level="INFO",
        event="adapter_completed",
        request_id=request_id,
        module="practice.bind",
        outcome=attempt_id,
        started=started,
    )
    rendered = render_paper(
        paper.paper_id,
        approvals,
        auth,
        store,
        files,
        renderer,
        logger,
        request_id,
        actor_teacher_id=actor_teacher_id,
    )
    if isinstance(rendered, Err):
        current = store.get_paper(paper.paper_id) or paper
        return Ok(
            OpenedPaper(
                paper=current,
                fixture_answer_id=attempt_id,
                render_code=rendered.code,
                render_message=rendered.message,
            )
        )
    return Ok(
        OpenedPaper(
            paper=rendered.value,
            fixture_answer_id=attempt_id,
            render_code=None,
            render_message="",
        )
    )


def read_attempt(
    paper_id: str,
    auth: Authorizer,
    store: PracticeStore,
    logger: Logger,
    request_id: str,
    *,
    actor_teacher_id: str,
) -> Ok[AttemptView] | Err:
    started = time.perf_counter()
    loaded = read_store(
        lambda: store.get_paper(paper_id),
        logger,
        request_id,
        "practice.bind",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    if paper is None:
        return _refuse(logger, request_id, started, "not_found", "the paper does not exist")
    if paper.teacher_id != actor_teacher_id or not auth.allow(
        actor_teacher_id, paper.student_id, paper.subject_id
    ):
        return _refuse(logger, request_id, started, "unauthorized", "this teacher cannot handle that paper")
    found = read_store(
        lambda: store.find_answer_for_paper(paper_id),
        logger,
        request_id,
        "practice.bind",
        started,
    )
    if isinstance(found, Err):
        return found
    answer = found.value
    if answer is None:
        return _refuse(logger, request_id, started, "answer_not_owned", "the answer is not bound to this student paper")
    return Ok(
        AttemptView(
            fixture_answer_id=answer.fixture_answer_id,
            paper_id=answer.paper_id,
            sub_question_id=answer.sub_question_id,
            review_version_id=answer.review_version_id,
            status=answer.status,
            answer_text=answer.answer_text,
        )
    )


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module="practice.bind",
        outcome=code,
        started=started,
    )
    return Err(code, message)
