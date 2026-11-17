"""Public catalog types. Other slices import this module and nothing under it."""

from __future__ import annotations

from typing import Protocol

from backend.catalog.domain.approval import copy_issue_snapshot, issuable_snapshot, issue_block
from backend.catalog.domain.draft import (
    DraftFile,
    QuestionDraft,
    parse_question_draft,
    publication_blocked,
)
from backend.catalog.domain.snapshot import ApprovalSnapshot, IssueSnapshot

__all__ = [
    "ApprovalPort",
    "ApprovalSnapshot",
    "DraftFile",
    "IssueSnapshot",
    "QuestionDraft",
    "copy_issue_snapshot",
    "issuable_snapshot",
    "issue_block",
    "parse_question_draft",
    "publication_blocked",
]


class ApprovalPort(Protocol):
    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        """Return the version, or None when it does not exist."""
