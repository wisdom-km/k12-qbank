"""Build a job from stores. This module does not import another slice."""

from __future__ import annotations

from backend.ai.domain.grade import blank_count_of, question_type
from backend.ai.domain.records import Context, Run, WorkItem


def load_context(stores: object, run: Run) -> Context | None:
    intake = getattr(stores, "intake")
    practice = getattr(stores, "practice")
    items_store = getattr(stores, "items")
    files = getattr(stores, "files")
    page = intake.get(run.intake_id)
    if page is None or page.archived_at:
        return None
    paper = practice.get_paper(page.paper_id)
    if paper is None:
        return None
    image = files.read(page.file_id)
    if not image:
        return None
    work: list[WorkItem] = []
    for item in items_store.items_of(page.paper_id):
        boxes = tuple(item.boxes)
        on_page = item.page_no == page.page_no or any(box.page_no == page.page_no for box in boxes)
        if not on_page:
            continue
        snapshot = _snapshot(stores, item.question_version_id)
        snap_type = "" if snapshot is None else str(getattr(snapshot, "type", "") or "")
        option_text = str(getattr(item, "option_text", "") or "")
        stem = str(getattr(item, "stem_text", "") or "")
        kinds = tuple(str(getattr(box, "kind", "") or "") for box in boxes)
        kind = question_type(snap_type, option_text, stem, kinds)
        points = tuple(
            (float(box.x), float(box.y), float(box.w), float(box.h))
            for box in boxes
            if box.page_no == page.page_no
        )
        work.append(
            WorkItem(
                order_no=int(item.order_no),
                question_type=kind,
                stem=stem,
                standard_answer=str(getattr(item, "answer_text", "") or ""),
                boxes=points,
                blank_count=blank_count_of(stem) if kind == "fill_blank" else 0,
            )
        )
    return Context(
        run_id=run.run_id,
        intake_id=run.intake_id,
        paper_id=str(page.paper_id),
        page_no=int(page.page_no),
        image=image,
        items=tuple(work),
        expected_external_id=str(getattr(paper, "printed_external_id", "") or ""),
        provider=run.provider,
        model_name=run.model,
        prompt_version=run.prompt_version,
    )


def _snapshot(stores: object, question_version_id: str) -> object | None:
    approvals = getattr(stores, "approvals", None)
    reader = getattr(approvals, "read_snapshot", None)
    if reader is None:
        return None
    return reader(question_version_id)
