"""Public catalog types. Other slices import this module and nothing under it."""

from __future__ import annotations

from typing import Protocol

from backend.catalog.domain.approval import copy_issue_snapshot, issue_block
from backend.catalog.domain.snapshot import ApprovalSnapshot, IssueSnapshot

__all__ = [
    "ApprovalPort",
    "ApprovalSnapshot",
    "IssueSnapshot",
    "copy_issue_snapshot",
    "issue_block",
]


class ApprovalPort(Protocol):
    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        """Return the version, or None when it does not exist."""
