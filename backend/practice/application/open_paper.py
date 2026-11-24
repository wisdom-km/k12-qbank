"""Issue one paper and bind the synthetic attempt as one store write, then render."""

from __future__ import annotations

import time
from collections.abc import Callable

from backend.catalog.api import ApprovalPort, Publications
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import AttemptView, IssuePaperCommand, OpenedPaper
from dataclasses import replace

from backend.practice.application.issue_flow import place_flow
from backend.practice.application.issue_paper import gate_active_publication, prepare_issue
from backend.practice.application.ports import Authorizer, FileStore, PageRenderer, PracticeItems, PracticeStore
from backend.practice.application.render_paper import render_paper
from backend.practice.domain.confirm import PendingAnswer
from backend.practice.domain.formula import FormulaFault, fault_message, needs_structure, plain_has_command
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.page_layout import draw_legacy_formula, pack_items


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
    attempt_text: str,
    publications: Publications,
    items: PracticeItems | None = None,
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
    snapshot = approvals.read_snapshot(paper.question_version_id)
    seed = PracticeItem(
        paper_id=paper.paper_id,
        order_no=1,
        question_version_id=paper.question_version_id,
        answer_version_id=paper.answer_version_id,
        stem_text=prepared.value.stem,
        answer_text=prepared.value.answer_text,
        option_text=prepared.value.option_text,
        stem_parts=None if snapshot is None else snapshot.stem_parts,
        option_parts=None if snapshot is None else snapshot.option_parts,
    )
    copied = seed
    if command.layout_kind == "flow":
        if snapshot is None:
            return _refuse(
                logger,
                request_id,
                time.perf_counter(),
                "question_not_approved",
                "the question version is not approved",
            )
        flowed = place_flow((seed,), (snapshot,))
        if isinstance(flowed, Err):
            return _refuse(logger, request_id, time.perf_counter(), flowed.code, flowed.message)
        copied = flowed[0][0]
        paper = replace(paper, layout_kind="flow", layout_params=flowed[1], slots_per_page=1)
    else:
        blocked_formula = _formula_block(seed, paper.slots_per_page)
        if isinstance(blocked_formula, Err):
            return _refuse(
                logger, request_id, time.perf_counter(), blocked_formula.code, blocked_formula.message
            )
        copied = blocked_formula
    if plain_has_command(paper.formula):
        paper = replace(paper, formula="")
    if not attempt_text.strip():
        return _refuse(
            logger,
            request_id,
            time.perf_counter(),
            "attempt_missing",
            "the synthetic attempt text is empty",
        )
    blocked = gate_active_publication(publications, paper, logger, request_id)
    if blocked is not None:
        return blocked
    attempt_id = "fixture-answer-" + paper.paper_id
    answer = PendingAnswer(
        fixture_answer_id=attempt_id,
        paper_id=paper.paper_id,
        sub_question_id=paper.item_order[0],
        review_version_id=paper.review_version_id,
        student_id=paper.student_id,
        status="pending",
        answer_text=attempt_text,
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
    if items is not None:
        stored_item = read_store(
            lambda: items.set_items(paper.paper_id, (copied,)),
            logger,
            request_id,
            "practice.issue",
            started,
        )
        if isinstance(stored_item, Err):
            return stored_item
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
        items=items,
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
    if not paper.item_order:
        return _refuse(logger, request_id, started, "not_frozen", "the paper has no item order")
    sub_question_id = paper.item_order[0]
    found = read_store(
        lambda: store.find_answer_for_review(paper_id, sub_question_id, paper.review_version_id),
        logger,
        request_id,
        "practice.bind",
        started,
    )
    if isinstance(found, Err):
        return found
    answer = found.value
    if answer is None:
        return _refuse(
            logger,
            request_id,
            started,
            "attempt_not_current",
            "this review version has no attempt yet",
        )
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


def _formula_block(item: PracticeItem, slots_per_page: int) -> PracticeItem | Err:
    if needs_structure(item.stem_parts, item.stem_text, item.option_parts, item.option_text):
        code, message = fault_message(item.question_version_id, "formula_unstructured")
        return Err(code, message)
    try:
        if slots_per_page > 1:
            return pack_items((item,), slots_per_page)[0]
        return draw_legacy_formula(item)
    except FormulaFault as fault:
        code, message = fault_message(
            fault.question_version_id or item.question_version_id, fault.code, fault.command
        )
        return Err(code, message)


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
