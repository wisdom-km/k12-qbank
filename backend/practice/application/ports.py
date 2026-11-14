"""Ports the practice use cases call. Adapters implement these. No framework types."""

from __future__ import annotations

from typing import Protocol

from backend.practice.domain.confirm import Confirmation
from backend.practice.domain.paper import Paper


class Authorizer(Protocol):
    def allow(self, teacher_id: str, student_id: str, subject_id: str) -> bool:
        """Whether this teacher may handle this student and subject."""


class PracticeStore(Protocol):
    def add_paper(self, paper: Paper) -> None:
        """Store one new paper."""

    def get_paper(self, paper_id: str) -> Paper | None:
        """Return the paper, or None when it does not exist."""

    def get_confirmation(self, operation_key: str) -> Confirmation | None:
        """Return the confirmation stored for this key, or None."""

    def find_slot(self, paper_id: str, sub_question_id: str, review_version_id: str) -> str | None:
        """Return the operation key that already holds this review, or None."""

    def add_confirmation(self, record: Confirmation) -> None:
        """Store one new confirmation."""
