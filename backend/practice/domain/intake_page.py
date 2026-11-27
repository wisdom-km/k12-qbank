"""One received page. The current row is the one without superseded_at."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntakePage:
    intake_id: str
    paper_id: str
    page_no: int
    file_id: str
    checksum: str
    uploaded_by: str
    uploaded_at: str
    located_by: str
    superseded_at: str | None = None
    archived_at: str | None = None


def paper_page_count(layout_kind: str, slots_per_page: int, page_numbers: tuple[int, ...]) -> int:
    """Flow and packed papers use the highest page. One item per page uses the count.

    A paper with no items is one page. The number is the count, not a hole list.
    """
    if not page_numbers:
        return 1
    if layout_kind == "flow" or slots_per_page > 1:
        return max(max(number, 1) for number in page_numbers)
    return len(page_numbers)
