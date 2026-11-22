"""In-memory publication rows. This adapter does not run V007."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import replace

from backend.catalog.domain.publication import Publication, require_actor
from backend.catalog.domain.snapshot import ApprovalSnapshot


class MemoryPublications:
    def __init__(self) -> None:
        self._rows: dict[str, Publication] = {}
        self._lock = threading.Lock()

    def put(self, publication: Publication) -> None:
        with self._lock:
            self._rows[publication.publication_id] = publication

    def active_of(self, question_version_id: str, answer_version_id: str) -> Publication | None:
        with self._lock:
            rows = list(self._rows.values())
        for row in rows:
            if row.status != "active":
                continue
            if row.question_version_id == question_version_id and row.answer_version_id == answer_version_id:
                return row
        return None

    def list_active(self) -> tuple[Publication, ...]:
        with self._lock:
            rows = [row for row in self._rows.values() if row.status == "active"]
        return tuple(sorted(rows, key=lambda row: row.publication_id))

    def rows_for(self, question_version_id: str, answer_version_id: str) -> tuple[Publication, ...]:
        with self._lock:
            rows = [
                row
                for row in self._rows.values()
                if row.question_version_id == question_version_id and row.answer_version_id == answer_version_id
            ]
        return tuple(sorted(rows, key=lambda row: row.publication_id))

    def retire_by_binding(self, q_vid: str, a_vid: str, actor: str | None) -> str:
        require_actor(actor)
        with self._lock:
            chosen = [
                row
                for row in self._rows.values()
                if row.question_version_id == q_vid and row.answer_version_id == a_vid
            ]
            active = [row for row in chosen if row.status == "active"]
            if active:
                row = active[0]
                self._rows[row.publication_id] = replace(row, status="retired")
                return "retired"
            if any(row.status == "retired" for row in chosen):
                return "already_retired"
            return "not_found"

    def fill_grandfather(self, snapshots: Sequence[ApprovalSnapshot]) -> None:
        """Same filter as the V007 INSERT. Memory tests call this. PostgreSQL runs the SQL."""
        for snap in snapshots:
            if not snap.question_approved or not snap.answer_approved or snap.retired:
                continue
            self.put(
                Publication(
                    publication_id=f"pub-{snap.question_version_id}-{snap.answer_version_id}",
                    question_version_id=snap.question_version_id,
                    answer_version_id=snap.answer_version_id,
                    subject_id=snap.subject_id,
                    status="active",
                )
            )
