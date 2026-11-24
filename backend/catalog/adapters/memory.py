"""In-memory approval snapshots for tests and the local skeleton."""

from __future__ import annotations

import threading
from dataclasses import replace

from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.result import StoreFault


class MemoryApprovals:
    def __init__(self) -> None:
        self._items: dict[str, ApprovalSnapshot] = {}
        self._lock = threading.Lock()

    def put(self, snapshot: ApprovalSnapshot) -> None:
        with self._lock:
            self._items[snapshot.question_version_id] = snapshot

    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        with self._lock:
            return self._items.get(question_version_id)

    def list_snapshots(self) -> tuple[ApprovalSnapshot, ...]:
        with self._lock:
            rows = sorted(self._items.values(), key=lambda item: item.question_version_id)
        return tuple(rows)

    def require_snapshot(self, question_version_id: str) -> ApprovalSnapshot:
        found = self.read_snapshot(question_version_id)
        if found is None:
            raise StoreFault("snapshot_not_found")
        return found

    def has_version_id(self, version_id: str) -> bool:
        with self._lock:
            return self._contains(version_id)

    def set_answer_space(self, question_version_id: str, space: str | None) -> None:
        """Update only the answer-space field. Other snapshot fields stay."""
        with self._lock:
            current = self._items.get(question_version_id)
            if current is None:
                return
            self._items[question_version_id] = replace(current, answer_space=space)

    def insert_if_absent(self, snapshot: ApprovalSnapshot) -> bool:
        """Insert one new version. A taken question id or answer id inserts nothing."""
        with self._lock:
            if self._contains(snapshot.question_version_id) or self._contains(snapshot.answer_version_id):
                return False
            self._items[snapshot.question_version_id] = snapshot
            return True

    def replace_if_current(self, expected: ApprovalSnapshot, updated: ApprovalSnapshot) -> bool:
        """Store updated only while the row is still expected. A stale snapshot does not write."""
        if updated.question_version_id != expected.question_version_id:
            return False
        with self._lock:
            current = self._items.get(expected.question_version_id)
            if current != expected:
                return False
            self._items[updated.question_version_id] = updated
            return True

    def _contains(self, version_id: str) -> bool:
        if version_id in self._items:
            return True
        return any(item.answer_version_id == version_id for item in self._items.values())
