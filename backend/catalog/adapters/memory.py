"""In-memory approval snapshots for tests and the local skeleton."""

from __future__ import annotations

from backend.catalog.domain.snapshot import ApprovalSnapshot


class MemoryApprovals:
    def __init__(self) -> None:
        self._items: dict[str, ApprovalSnapshot] = {}

    def put(self, snapshot: ApprovalSnapshot) -> None:
        self._items[snapshot.question_version_id] = snapshot

    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        return self._items.get(question_version_id)
