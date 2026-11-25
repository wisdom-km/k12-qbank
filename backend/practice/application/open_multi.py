"""Issue one paper that holds two or more frozen questions, then render it."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from backend.catalog.api import ApprovalPort, Publications
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import OpenedPaper
from backend.practice.application.compose_multi import compose_multi_item_paper
from backend.practice.application.issue_flow import place_flow
from backend.practice.application.ports import Authorizer, ComposedPaperStore, FileStore, PageRenderer, PracticeItems, PracticeStore
from backend.practice.application.render_paper import render_paper
from backend.practice.domain.confirm import PendingAnswer
from backend.practice.domain.item import PracticeItem


def open_multi_paper(
    *,
    teacher_id: str,
    student_id: str,
    subject_id: str,
    review_version_id: str,
    question_version_ids: Sequence[str],
    qr_printed: bool,
    printed_external_id: str,
    slots_per_page: int = 1,
    layout_kind: str = "slots",
    approvals: ApprovalPort,
    auth: Authorizer,
    store: PracticeStore,
    items: PracticeItems,
    writer: ComposedPaperStore,
    files: FileStore,
    renderer: PageRenderer,
    logger: Logger,
    request_id: str,
    attempt_text: str,
    publications: Publications,
    bind_attempt: bool = True,
) -> Ok[OpenedPaper] | Err:
    """Copy each approved stem and answer, then draw the packed pages."""
    started = time.perf_counter()
    if len(question_version_ids) < 2:
        return _refuse(logger, request_id, started, "not_multi", "a multi-item paper needs at least two items")
    if not review_version_id.strip() or (bind_attempt and not attempt_text.strip()):
        return _refuse(logger, request_id, started, "attempt_missing", "the synthetic attempt text is empty")
    if not auth.allow(teacher_id, student_id, subject_id):
        return _refuse(logger, request_id, started, "unauthorized", "this teacher cannot issue for that student and subject")
    paper_id = uuid.uuid4().hex
    built: list[PracticeItem] = []
    for order_no, version_id in enumerate(question_version_ids, start=1):
        loaded = read_store(
            lambda version_id=version_id: approvals.read_snapshot(version_id),
            logger,
            request_id,
            "practice.issue",
            started,
        )
        if isinstance(loaded, Err):
            return loaded
        snapshot = loaded.value
        if snapshot is None or not snapshot.question_approved:
            return _refuse(logger, request_id, started, "question_not_approved", "the question version is not approved")
        if snapshot.subject_id != subject_id:
            return _refuse(logger, request_id, started, "subject_mismatch", "the requested subject does not match the catalog record")
        if order_no == 1 and not snapshot.item_order:
            return _refuse(logger, request_id, started, "not_frozen", "the paper has no item order")
        built.append(
            PracticeItem(
                paper_id=paper_id,
                order_no=order_no,
                question_version_id=version_id,
                answer_version_id=snapshot.answer_version_id,
                stem_text=snapshot.stem,
                answer_text=snapshot.answer_text,
                option_text="\n".join(snapshot.options),
                stem_parts=snapshot.stem_parts,
                option_parts=snapshot.option_parts,
            )
        )
    layout_params = ""
    if layout_kind == "flow":
        snapshots = []
        for version_id in question_version_ids:
            found = approvals.read_snapshot(version_id)
            if found is None:
                return _refuse(logger, request_id, started, "question_not_approved", "the question version is not approved")
            snapshots.append(found)
        flowed = place_flow(tuple(built), tuple(snapshots))
        if isinstance(flowed, Err):
            return _refuse(logger, request_id, started, flowed.code, flowed.message)
        built = list(flowed[0])
        layout_params = flowed[1]
        slots_per_page = 1
    composed = compose_multi_item_paper(
        paper_id,
        tuple(built),
        teacher_id=teacher_id,
        student_id=student_id,
        review_version_id=review_version_id,
        approvals=approvals,
        publications=publications,
        writer=writer,
        qr_printed=qr_printed,
        printed_external_id=printed_external_id,
        slots_per_page=slots_per_page,
        layout_kind=layout_kind,
        layout_params=layout_params,
    )
    if isinstance(composed, Err):
        return _refuse(logger, request_id, started, composed.code, composed.message)
    paper = composed.value
    attempt_id = ""
    if bind_attempt:
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
        saved = read_store(
            lambda: store.put_answer(answer),
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
    rendered = render_paper(
        paper.paper_id,
        approvals,
        auth,
        store,
        files,
        renderer,
        logger,
        request_id,
        actor_teacher_id=teacher_id,
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


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
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
