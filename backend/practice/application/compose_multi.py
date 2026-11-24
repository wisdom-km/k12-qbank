"""Compose one multi-item paper. A refusal writes no paper, page, or item row."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from backend.catalog.api import ApprovalPort, Publications
from backend.kernel.result import Err, Ok
from backend.practice.application.ports import ComposedPaperStore
from backend.practice.domain.item import PracticeItem, stored_item
from backend.practice.domain.page_face import formula_from_stem
from backend.practice.domain.page_layout import pack_items
from backend.practice.domain.paper import Paper, freeze_paper


def compose_multi_item_paper(
    paper_id: str,
    items: Sequence[PracticeItem],
    *,
    teacher_id: str,
    student_id: str,
    review_version_id: str,
    approvals: ApprovalPort,
    publications: Publications,
    writer: ComposedPaperStore,
    qr_printed: bool = False,
    printed_external_id: str = "",
    slots_per_page: int = 1,
    layout_kind: str = "slots",
    layout_params: str = "",
) -> Ok[Paper] | Err:
    """Freeze two or more items. The paper column keeps items[0] for old readers."""
    shape = _shape_error(paper_id, items)
    if shape is not None:
        return shape
    for item in items:
        refused = _is_item_approved(item, approvals)
        if refused is not None:
            return refused
    for item in items:
        if publications.active_of(item.question_version_id, item.answer_version_id) is None:
            return Err(
                "no_active_publication",
                "the question version and the answer version have no active publication",
            )
    first = approvals.read_snapshot(items[0].question_version_id)
    if first is None:
        return Err("question_not_approved", "the question version is not approved")
    paper = freeze_paper(
        paper_id=paper_id,
        teacher_id=teacher_id,
        student_id=student_id,
        subject_id=first.subject_id,
        question_version_id=items[0].question_version_id,
        answer_version_id=items[0].answer_version_id,
        asset_ids=tuple(first.asset_ids),
        layout_template_id=first.layout_template_id,
        review_version_id=review_version_id,
        item_order=tuple(first.item_order),
        formula=formula_from_stem(first.stem),
        qr_printed=qr_printed,
        printed_external_id=printed_external_id,
        slots_per_page=slots_per_page,
        layout_kind=layout_kind,
        layout_params=layout_params,
        issued_on=datetime.now(timezone.utc).date().isoformat(),
    )
    if isinstance(paper, Err):
        return paper
    stored = tuple(stored_item(paper_id, item) for item in items)
    if layout_kind != "flow" and slots_per_page > 1:
        stored = pack_items(stored, slots_per_page)
    writer.place_composed(paper, stored)
    return Ok(paper)


def _is_item_approved(item: PracticeItem, approvals: ApprovalPort) -> Err | None:
    """The bound snapshot answer is the applicable answer. Check in this order."""
    snap = approvals.read_snapshot(item.question_version_id)
    if snap is None:
        return Err("question_not_approved", "the question version is not approved")
    if not snap.question_approved:
        return Err("question_not_approved", "the question version is not approved")
    if not snap.answer_approved:
        return Err("answer_not_approved", "the answer version is not approved")
    if snap.answer_version_id != item.answer_version_id:
        return Err("answer_not_applicable", "the answer version is not the applicable one")
    return None


def _shape_error(paper_id: str, items: Sequence[PracticeItem]) -> Err | None:
    if len(items) < 2:
        return Err("not_multi", "a multi-item paper needs at least two items")
    seen: set[int] = set()
    for item in items:
        if item.paper_id != paper_id or item.order_no < 1 or item.order_no in seen:
            return Err("bad_order", "order_no must be positive and unique on this paper")
        seen.add(item.order_no)
    return None



