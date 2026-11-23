"""Public catalog types. Other slices import this module and nothing under it."""

from __future__ import annotations

from typing import Literal, Protocol

from backend.catalog.domain.answer import AnswerDraft, parse_answer_draft, answer_not_publication
from backend.catalog.domain.approval import copy_issue_snapshot, issuable_snapshot, issue_block
from backend.catalog.domain.parse import parse_question_draft
from backend.catalog.domain.validate import DraftFile, QuestionDraft, publication_blocked
from backend.catalog.domain.publication import Asset, AttachResult, Publication, RemoveResult
from backend.catalog.domain.snapshot import ApprovalSnapshot, IssueSnapshot

__all__ = [
    "AnswerDraft",
    "ApprovalPort",
    "ApprovalSnapshot",
    "Asset",
    "AttachResult",
    "DraftFile",
    "IssueSnapshot",
    "Publication",
    "Publications",
    "RemoveResult",
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

    def rows_for(self, question_version_id: str, answer_version_id: str) -> tuple[Publication, ...]:
        """Every row for this binding, any status. Empty when the pair was never written."""

    def put(self, publication: Publication) -> None:
        """Insert one row. Callers check rows_for before writing over a retired binding."""

    def retire_by_binding(self, q_vid: str, a_vid: str, actor: str | None) -> str:
        """Return retired, already_retired, or not_found. An empty actor raises StoreFault."""

    def publish_by_binding(
        self,
        question_version_id: str,
        answer_version_id: str,
        actor: str,
        layout_template_id: str | None = None,
    ) -> str:
        """Return published, already_active, or not_approved. Subject comes from the approval row."""

    def list_page(
        self,
        question_version_id: str | None = None,
        answer_version_id: str | None = None,
        subject_id: str | None = None,
        status: Literal["active", "retired"] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[tuple[Publication, ...], int]:
        """One page of publication rows and the filtered total. The port does not look at a role."""

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
        """Attach one file. An empty actor raises StoreFault. A retired publication is refused."""

    def remove_asset(self, publication_id: str, publication_asset_id: str, actor_id: str) -> RemoveResult:
        """Delete one asset. A different publication id is not_found and the row stays."""

    def list_assets(self, publication_id: str) -> tuple[Asset, ...] | None:
        """Assets ordered by created_at, then id. None when the publication does not exist."""
