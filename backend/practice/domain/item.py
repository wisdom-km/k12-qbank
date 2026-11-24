"""One frozen row of a multi-item practice. Score stays empty without an institution rule."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PracticeItem:
    """order_no is the frozen sequence. The paper row still keeps its own compatibility ids.

    page_no, slot_no, and slot_span are the issue-time slot. Old rows default to 1.
    option_text is the frozen choice lines. A later catalog edit does not change them.
    """

    paper_id: str
    order_no: int
    question_version_id: str
    answer_version_id: str
    score: int | None = None
    stem_text: str = ""
    answer_text: str = ""
    page_no: int = 1
    slot_no: int = 1
    slot_span: int = 1
    option_text: str = ""
    placed_lines: tuple[tuple[str, float, float], ...] = ()
    boxes: tuple[ItemBox, ...] = ()


@dataclass(frozen=True)
class ItemBox:
    """One answer box stored at issue time. Coordinates are PDF points."""

    box_no: int
    page_no: int
    x: float
    y: float
    w: float
    h: float
    kind: str


def stored_item(paper_id: str, item: PracticeItem) -> PracticeItem:
    """Copy every frozen field onto this paper. New fields must not be dropped."""
    return replace(item, paper_id=paper_id)


class PaperEmpty(Exception):
    """The paper is missing, or it has no question version to fall back to."""

    def __init__(self, paper_id: str) -> None:
        self.paper_id = paper_id
        super().__init__(paper_id)
