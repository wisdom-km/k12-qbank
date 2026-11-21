"""Resolve the frozen item list. Empty practice_item rows fall back to the paper column."""

from __future__ import annotations

from backend.practice.application.ports import PracticeItems, PracticeStore
from backend.practice.domain.item import PaperEmpty, PracticeItem


def _resolve_items(
    paper_id: str,
    store: PracticeStore,
    items: PracticeItems | None,
) -> tuple[PracticeItem, ...]:
    found = () if items is None else items.items_of(paper_id)
    if found:
        return found
    paper = store.get_paper(paper_id)
    version = None if paper is None else paper.question_version_id
    if paper is None or version is None or not str(version).strip():
        raise PaperEmpty(paper_id)
    return (
        PracticeItem(
            paper_id=paper_id,
            order_no=1,
            question_version_id=paper.question_version_id,
            answer_version_id=paper.answer_version_id,
            score=None,
        ),
    )
