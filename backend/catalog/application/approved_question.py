"""Approved questions a tag may cite. Wraps read_snapshot. Does not import knowledge."""

from __future__ import annotations

from typing import Protocol

from backend.catalog.domain.snapshot import ApprovalSnapshot


class _Approvals(Protocol):
    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        """Return the version, or None when it does not exist."""


class ApprovedQuestionReader:
    """Read-only seam. None means missing, unapproved, retired, or subject-less."""

    def __init__(self, approvals: _Approvals) -> None:
        self._approvals = approvals

    def approved(self, question_version_id: str) -> ApprovalSnapshot | None:
        snapshot = self._approvals.read_snapshot(question_version_id)
        if not _taggable(snapshot):
            return None
        return snapshot


def _taggable(snapshot: ApprovalSnapshot | None) -> bool:
    if snapshot is None or snapshot.retired:
        return False
    if not snapshot.question_approved or not snapshot.answer_approved:
        return False
    if not snapshot.subject_id.strip() or not snapshot.question_version_id.strip():
        return False
    return True
