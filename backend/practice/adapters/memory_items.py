"""In-memory practice items. An empty list is the single-item fallback."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from backend.practice.adapters.memory import MemoryPractice
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import Paper


class MemoryPracticeItems:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, int], PracticeItem] = {}
        self._lock = threading.Lock()

    def items_of(self, paper_id: str) -> tuple[PracticeItem, ...]:
        with self._lock:
            found = [item for (stored_id, _), item in self._rows.items() if stored_id == paper_id]
        found.sort(key=lambda item: item.order_no)
        return tuple(found)

    def set_items(self, paper_id: str, items: Sequence[PracticeItem]) -> None:
        """Delete this paper's rows, then insert the given sequence. Empty is legal."""
        stored = tuple(_stored(paper_id, item) for item in items)
        with self._lock:
            self._rows = {key: item for key, item in self._rows.items() if key[0] != paper_id}
            for item in stored:
                self._rows[(paper_id, item.order_no)] = item


class MemoryComposedWriter:
    """Memory has no page table. The paper row and the item rows are the unit."""

    def __init__(self, store: MemoryPractice, items: MemoryPracticeItems) -> None:
        self._store = store
        self._items = items

    def place_composed(self, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
        self._store.add_paper(paper)
        self._items.set_items(paper.paper_id, items)


def _stored(paper_id: str, item: PracticeItem) -> PracticeItem:
    return PracticeItem(
        paper_id=paper_id,
        order_no=item.order_no,
        question_version_id=item.question_version_id,
        answer_version_id=item.answer_version_id,
        score=item.score,
    )
