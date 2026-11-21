"""Public catalog types. Other slices import this module and nothing under it."""

from __future__ import annotations

from typing import Protocol

from backend.catalog.domain.answer import AnswerDraft, parse_answer_draft, answer_not_publication
from backend.catalog.domain.approval import copy_issue_snapshot, issuable_snapshot, issue_block
from backend.catalog.domain.parse import parse_question_draft
from backend.catalog.domain.validate import DraftFile, QuestionDraft, publication_blocked
from backend.catalog.domain.publication import Publication
from backend.catalog.domain.snapshot import ApprovalSnapshot, IssueSnapshot

__all__ = [
    "AnswerDraft",
    "ApprovalPort",
    "ApprovalSnapshot",
    "DraftFile",
    "IssueSnapshot",
    "Publication",
    "Publications",
    "QuestionDraft",
    "answer_not_publication",
    "copy_issue_snapshot",
    "issuable_snapshot",
    "issue_block",
    "parse_answer_draft",
    "parse_question_draft",
    "publication_blocked",
]


class ApprovalPort(Protocol):
    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        """Return the version, or None when it does not exist."""


class Publications(Protocol):
    def active_of(self, question_version_id: str, answer_version_id: str) -> Publication | None:
        """Return the active binding, or None when that pair is not active."""

    def list_active(self) -> tuple[Publication, ...]:
        """Every active row. Contract tests use this. Issue paths call active_of."""
