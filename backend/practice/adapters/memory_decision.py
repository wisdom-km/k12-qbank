"""In-memory teacher decisions. One current row per paper item."""

from __future__ import annotations

import threading
from dataclasses import replace

from backend.practice.domain.decision import TeacherDecision


class MemoryDecisions:
    def __init__(self) -> None:
        self._rows: dict[str, TeacherDecision] = {}
        self._lock = threading.Lock()

    def current(self, paper_id: str, order_no: int) -> TeacherDecision | None:
        with self._lock:
            return self._current(paper_id, order_no)

    def currents(self, paper_id: str) -> tuple[TeacherDecision, ...]:
        with self._lock:
            rows = [
                row
                for row in self._rows.values()
                if row.paper_id == paper_id and not row.voided_at
            ]
        return tuple(sorted(rows, key=lambda row: row.order_no))

    def history(self, paper_id: str) -> tuple[TeacherDecision, ...]:
        with self._lock:
            rows = [row for row in self._rows.values() if row.paper_id == paper_id]
        return tuple(sorted(rows, key=lambda row: (row.order_no, row.decided_at, row.decision_id)))

    def replace(self, row: TeacherDecision) -> None:
        """Void the current row, then insert. The new row is the only current one."""
        with self._lock:
            current = self._current(row.paper_id, row.order_no)
            if current is not None:
                self._rows[current.decision_id] = replace(current, voided_at=row.decided_at)
            self._rows[row.decision_id] = row

    def _current(self, paper_id: str, order_no: int) -> TeacherDecision | None:
        for row in self._rows.values():
            if row.paper_id == paper_id and row.order_no == order_no and not row.voided_at:
                return row
        return None
