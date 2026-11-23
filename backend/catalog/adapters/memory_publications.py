"""In-memory publication rows. This adapter does not run V007."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Literal

from backend.catalog.domain.publication import (
    Asset,
    AttachResult,
    Publication,
    RemoveResult,
    RetireCode,
    asset_file_refusal,
    asset_id_for,
    bound_page,
    clean_layout,
    require_actor,
    require_subject,
)
from backend.catalog.domain.snapshot import ApprovalSnapshot


class MemoryPublications:
    def __init__(self) -> None:
        self._rows: dict[str, Publication] = {}
        self._assets: dict[str, Asset] = {}
        self._asset_key: dict[tuple[str, str], str] = {}
        self._page_files: set[str] = set()
        self._paper_files: set[str] = set()
        self._paper_checksums: set[str] = set()
        self._clock = datetime.now(timezone.utc)
        self._lock = threading.Lock()
        self._approvals: object | None = None

    def attach_approvals(self, approvals: object) -> None:
        """Memory has no shared transaction. Compose wires the approval book here."""
        self._approvals = approvals

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

    def list_page(
        self,
        question_version_id: str | None = None,
        answer_version_id: str | None = None,
        subject_id: str | None = None,
        status: Literal["active", "retired"] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[tuple[Publication, ...], int]:
        page_offset, page_limit = bound_page(offset, limit)
        with self._lock:
            rows = list(self._rows.values())
        chosen = [
            row
            for row in rows
            if _matches(row, question_version_id, answer_version_id, subject_id, status)
        ]
        chosen.sort(key=lambda row: row.publication_id)
        page = tuple(chosen[page_offset : page_offset + page_limit])
        return page, len(chosen)

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
                return RetireCode(
                    "retired",
                    publication_id=row.publication_id,
                    subject_id=row.subject_id,
                )
            if any(row.status == "retired" for row in chosen):
                return RetireCode("already_retired")
            return RetireCode("not_found")

    def publish_by_binding(
        self,
        question_version_id: str,
        answer_version_id: str,
        actor: str,
        layout_template_id: str | None = None,
    ) -> str:
        require_actor(actor)
        layout = clean_layout(layout_template_id)
        with self._lock:
            snap = _read_approval(self._approvals, question_version_id)
            if snap is None or not _binding_approved(snap, answer_version_id):
                return "not_approved"
            require_subject(snap.subject_id)
            chosen = [
                row
                for row in self._rows.values()
                if row.question_version_id == question_version_id and row.answer_version_id == answer_version_id
            ]
            if any(row.status == "active" for row in chosen):
                return "already_active"
            seq = len(chosen) + 1
            publication_id = f"pub-{question_version_id}-{answer_version_id}-{seq}"
            # _lock is not reentrant. put() would take it again and deadlock.
            self._rows[publication_id] = Publication(
                publication_id=publication_id,
                question_version_id=question_version_id,
                answer_version_id=answer_version_id,
                subject_id=snap.subject_id,
                status="active",
                layout_template_id=layout,
            )
            return "published"

    def note_page_file(self, file_id: str) -> None:
        """Test seam. Stands in for files.purpose = page. Memory has no files table."""
        with self._lock:
            self._page_files.add(file_id)

    def note_paper_file(self, file_id: str) -> None:
        """Test seam. Stands in for papers.file_id."""
        with self._lock:
            self._paper_files.add(file_id)

    def note_paper_checksum(self, checksum: str) -> None:
        """Test seam. Stands in for papers.file_checksum."""
        with self._lock:
            self._paper_checksums.add(checksum)

    def clear_privacy_notes(self) -> None:
        with self._lock:
            self._page_files.clear()
            self._paper_files.clear()
            self._paper_checksums.clear()

    def attach_asset(
        self,
        publication_id: str,
        file_id: str,
        kind: Literal["image", "pdf"],
        checksum: str,
        size_bytes: int,
        mime_type: str,
        actor_id: str,
    ) -> AttachResult:
        require_actor(actor_id)
        with self._lock:
            publication = self._rows.get(publication_id)
            if publication is None:
                return AttachResult("publication_not_found")
            if publication.status == "retired":
                return AttachResult("publication_retired")
            refusal = asset_file_refusal(
                file_id,
                kind,
                mime_type,
                page_file=file_id in self._page_files,
                paper_file=file_id in self._paper_files,
                paper_checksum=checksum in self._paper_checksums,
            )
            if refusal is not None:
                return AttachResult(refusal)
            existing = self._asset_key.get((publication_id, checksum))
            if existing is not None:
                return AttachResult("already_attached", publication_asset_id=existing)
            created_at = self._clock
            self._clock = created_at + timedelta(microseconds=1)
            asset = Asset(
                publication_asset_id=asset_id_for(publication_id, checksum),
                publication_id=publication_id,
                file_id=file_id,
                kind=kind,
                checksum=checksum,
                size_bytes=size_bytes,
                mime_type=mime_type,
                created_at=created_at,
                created_by=actor_id,
            )
            self._assets[asset.publication_asset_id] = asset
            self._asset_key[(publication_id, checksum)] = asset.publication_asset_id
            return AttachResult("attached", publication_asset_id=asset.publication_asset_id, asset=asset)

    def remove_asset(self, publication_id: str, publication_asset_id: str, actor_id: str) -> RemoveResult:
        require_actor(actor_id)
        with self._lock:
            asset = self._assets.get(publication_asset_id)
            if asset is None or asset.publication_id != publication_id:
                return RemoveResult("not_found")
            del self._assets[publication_asset_id]
            self._asset_key.pop((asset.publication_id, asset.checksum), None)
            return RemoveResult("removed", asset=asset)

    def list_assets(self, publication_id: str) -> tuple[Asset, ...] | None:
        with self._lock:
            if publication_id not in self._rows:
                return None
            rows = [asset for asset in self._assets.values() if asset.publication_id == publication_id]
        rows.sort(key=lambda asset: (asset.created_at, asset.publication_asset_id))
        return tuple(rows)

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


def _matches(
    row: Publication,
    question_version_id: str | None,
    answer_version_id: str | None,
    subject_id: str | None,
    status: str | None,
) -> bool:
    if question_version_id is not None and row.question_version_id != question_version_id:
        return False
    if answer_version_id is not None and row.answer_version_id != answer_version_id:
        return False
    if subject_id is not None and row.subject_id != subject_id:
        return False
    if status is not None and row.status != status:
        return False
    return True


def _read_approval(approvals: object | None, question_version_id: str) -> ApprovalSnapshot | None:
    if approvals is None:
        return None
    found = approvals.read_snapshot(question_version_id)  # type: ignore[attr-defined]
    if found is None:
        return None
    return found


def _binding_approved(snap: ApprovalSnapshot, answer_version_id: str) -> bool:
    if snap.answer_version_id != answer_version_id:
        return False
    if not snap.question_approved or not snap.answer_approved:
        return False
    return not snap.retired
