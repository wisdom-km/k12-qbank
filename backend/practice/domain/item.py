"""One frozen row of a multi-item practice. Score stays empty without an institution rule."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PracticeItem:
    """order_no is the frozen sequence. The paper row still keeps its own compatibility ids."""

    paper_id: str
    order_no: int
    question_version_id: str
    answer_version_id: str
    score: int | None = None


class PaperEmpty(Exception):
    """The paper is missing, or it has no question version to fall back to."""

    def __init__(self, paper_id: str) -> None:
        self.paper_id = paper_id
        super().__init__(paper_id)
