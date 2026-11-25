"""Issue one more paper from the current teacher decisions on a source paper."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence

from backend.catalog.api import ApprovalPort, Publications
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.api import IssuePaperCommand, OpenedPaper
from backend.practice.application.open_multi import open_multi_paper
from backend.practice.application.open_paper import open_paper
from backend.practice.application.ports import Authorizer, ComposedPaperStore, FileStore, PageRenderer, PracticeItems, PracticeStore
from backend.practice.domain.decision import TeacherDecision
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import Paper

_MODULE = "practice.follow_up"
_RETRY = frozenset({"incorrect", "partial", "blank"})


def issue_follow_up(
    paper_id: str,
    *,
    order_nos: Sequence[int],
    review_version_id: str,
    actor_teacher_id: str,
    approvals: ApprovalPort,
    auth: Authorizer,
    store: PracticeStore,
    items: PracticeItems,
    decisions: object,
    writer: ComposedPaperStore,
    files: FileStore,
    renderer: PageRenderer,
    publications: Publications,
    logger: Logger,
    request_id: str,
    qr_printed: bool,
    printed_external_id: str,
    attempt_text: str,
    bind_attempt: bool,
) -> Ok[OpenedPaper] | Err:
    """Copy confirmed items onto a new paper. The source paper is not rewritten."""
    started = time.perf_counter()
    loaded = read_store(lambda: store.get_paper(paper_id), logger, request_id, _MODULE, started)
    if isinstance(loaded, Err):
        return loaded
    source = loaded.value
    if source is None:
        return _refuse(logger, request_id, started, "not_found", "the paper does not exist")
    if source.teacher_id != actor_teacher_id or not auth.allow(
        actor_teacher_id, source.student_id, source.subject_id
    ):
        return _refuse(
            logger,
            request_id,
            started,
            "permission_denied",
            "this teacher cannot issue a follow-up for that paper",
        )
    found_items = read_store(lambda: tuple(items.items_of(paper_id)), logger, request_id, _MODULE, started)
    if isinstance(found_items, Err):
        return found_items
    found_decisions = read_store(
        lambda: tuple(decisions.currents(paper_id)),  # type: ignore[attr-defined]
        logger,
        request_id,
        _MODULE,
        started,
    )
    if isinstance(found_decisions, Err):
        return found_decisions
    selected = _select(order_nos, found_items.value, source, found_decisions.value)
    if isinstance(selected, Err):
        return _refuse(logger, request_id, started, selected.code, selected.message)
    for version_id in selected:
        snapshot = approvals.read_snapshot(version_id)
        if snapshot is not None and snapshot.retired:
            return _refuse(logger, request_id, started, "retired", "the question version is retired")
    review = review_version_id.strip() or source.review_version_id
    if len(selected) == 1:
        opened = open_paper(
            IssuePaperCommand(
                teacher_id=actor_teacher_id,
                student_id=source.student_id,
                subject_id=source.subject_id,
                question_version_id=selected[0],
                review_version_id=review,
                qr_printed=qr_printed,
                printed_external_id=printed_external_id,
                slots_per_page=1,
                layout_kind="flow",
            ),
            approvals,
            auth,
            store,
            files,
            renderer,
            logger,
            request_id,
            actor_teacher_id=actor_teacher_id,
            attempt_text=attempt_text,
            publications=publications,
            items=items,
            bind_attempt=bind_attempt,
            source_paper_id=source.paper_id,
        )
    else:
        opened = open_multi_paper(
            teacher_id=actor_teacher_id,
            student_id=source.student_id,
            subject_id=source.subject_id,
            review_version_id=review,
            question_version_ids=selected,
            qr_printed=qr_printed,
            printed_external_id=printed_external_id,
            slots_per_page=1,
            layout_kind="flow",
            approvals=approvals,
            auth=auth,
            store=store,
            items=items,
            writer=writer,
            files=files,
            renderer=renderer,
            logger=logger,
            request_id=request_id,
            attempt_text=attempt_text,
            publications=publications,
            bind_attempt=bind_attempt,
            source_paper_id=source.paper_id,
        )
    if isinstance(opened, Err):
        return opened
    _audit(logger, request_id, started, actor_teacher_id, source.paper_id, opened.value.paper.paper_id, len(selected))
    return opened


def _select(
    order_nos: Sequence[int],
    rows: Sequence[PracticeItem],
    source: Paper,
    current: Sequence[TeacherDecision],
) -> list[str] | Err:
    """Map confirmed order numbers to question versions. AI suggestions are not read."""
    by_order = {row.order_no: row.question_version_id for row in sorted(rows, key=lambda row: row.order_no)}
    if not by_order and source.question_version_id.strip():
        by_order = {1: source.question_version_id}
    decided = {row.order_no: row for row in current}
    requested = list(order_nos)
    if not requested:
        chosen = sorted(
            order
            for order, row in decided.items()
            if order in by_order and row.verdict in _RETRY
        )
    else:
        if any(_bad_order(order) for order in requested) or len(requested) != len(set(requested)):
            return Err("invalid_order_no", "the order number is missing, repeated, or not on this paper")
        if any(order not in by_order for order in requested):
            return Err("invalid_order_no", "the order number is missing, repeated, or not on this paper")
        if any(order not in decided for order in requested):
            return Err("decision_required", "that item has no current teacher decision")
        chosen = sorted(requested)
    if not chosen:
        return Err("no_retry_items", "there is no confirmed item to practice again")
    return [by_order[order] for order in chosen]


def _bad_order(order: object) -> bool:
    return isinstance(order, bool) or not isinstance(order, int) or order < 1


def _audit(
    logger: Logger,
    request_id: str,
    started: float,
    actor_id: str,
    source_paper_id: str,
    paper_id: str,
    item_count: int,
) -> None:
    detail = json.dumps(
        {"source_paper_id": source_paper_id, "paper_id": paper_id, "item_count": item_count},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    emit(
        logger,
        level="INFO",
        event="follow_up_paper_issued",
        request_id=request_id,
        module=_MODULE,
        outcome="ok",
        started=started,
        actor_user_id=actor_id,
        target_kind="paper",
        target_id=paper_id,
        audit=True,
        detail=detail,
        action="follow_up_paper_issued",
    )


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module=_MODULE,
        outcome=code,
        started=started,
    )
    return Err(code, message)
