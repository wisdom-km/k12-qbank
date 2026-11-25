"""In-memory intake pages. One current row per paper and page."""

from __future__ import annotations

import threading
from dataclasses import replace as replace_row

from backend.kernel.result import StoreFault
from backend.practice.domain.intake_page import IntakePage


class MemoryIntake:
    def __init__(self) -> None:
        self._rows: dict[str, IntakePage] = {}
        self._lock = threading.Lock()

    def get(self, intake_id: str) -> IntakePage | None:
        with self._lock:
            return self._rows.get(intake_id)

    def current(self, paper_id: str, page_no: int) -> IntakePage | None:
        with self._lock:
            return self._current(paper_id, page_no)

    def currents(self, paper_id: str) -> tuple[IntakePage, ...]:
        with self._lock:
            rows = [row for row in self._rows.values() if row.paper_id == paper_id and row.superseded_at is None]
        return tuple(sorted(rows, key=lambda row: row.page_no))

    def history(self, paper_id: str) -> tuple[IntakePage, ...]:
        """Every photo for this paper, including replaced ones."""
        with self._lock:
            rows = [row for row in self._rows.values() if row.paper_id == paper_id]
        return tuple(sorted(rows, key=lambda row: (row.page_no, row.uploaded_at, row.intake_id)))

    def file_purpose(self, file_id: str) -> str | None:
        """Memory has no files table. A page row cannot be rewritten here."""
        return None

    def count(self) -> int:
        with self._lock:
            return len(self._rows)

    def place(self, row: IntakePage, *, replace: bool) -> None:
        with self._lock:
            current = self._current(row.paper_id, row.page_no)
            if current is not None and not replace:
                raise StoreFault("page_already_received")
            if current is not None:
                self._rows[current.intake_id] = replace_row(current, superseded_at=row.uploaded_at)
            self._rows[row.intake_id] = row

    def _current(self, paper_id: str, page_no: int) -> IntakePage | None:
        for row in self._rows.values():
            if row.paper_id == paper_id and row.page_no == page_no and row.superseded_at is None:
                return row
        return None
