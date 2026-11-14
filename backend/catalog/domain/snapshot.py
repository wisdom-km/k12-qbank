"""Approved-or-not snapshot. Plain data. Practice copies the ids it needs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalSnapshot:
    question_version_id: str
    answer_version_id: str
    asset_ids: tuple[str, ...]
    layout_template_id: str
    question_approved: bool
    answer_approved: bool
    retired: bool


@dataclass(frozen=True)
class IssueSnapshot:
    """Versions copied onto a student paper at issue time.

    question_version_id and answer_version_id are frozen here. A later edit in
    the catalog does not change a paper that already holds this copy.
    """

    question_version_id: str
    answer_version_id: str
    asset_ids: tuple[str, ...]
    layout_template_id: str
