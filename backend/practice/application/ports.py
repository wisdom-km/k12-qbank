"""Ports the practice use cases call. Adapters implement these. No framework types."""

from __future__ import annotations

from typing import Protocol

from backend.kernel.result import Err
from backend.practice.domain.confirm import Confirmation, ConfirmationScope, PendingAnswer
from backend.practice.domain.paper import Paper


class Authorizer(Protocol):
    def allow(self, teacher_id: str, student_id: str, subject_id: str) -> bool:
        """Whether this teacher may handle this student and subject."""


class PracticeStore(Protocol):
    def add_paper(self, paper: Paper) -> None:
        """Store one new paper."""

    def get_paper(self, paper_id: str) -> Paper | None:
        """Return the paper, or None when it does not exist."""

    def get_confirmation(self, scope: ConfirmationScope) -> Confirmation | None:
        """Return the confirmation for this paper, sub-question, teacher, and key."""

    def find_slot(self, paper_id: str, sub_question_id: str, review_version_id: str) -> ConfirmationScope | None:
        """Return the scope that already holds this review slot, or None."""

    def put_answer(self, answer: PendingAnswer) -> None:
        """Store one server-loaded pending answer."""

    def set_review_version(self, paper_id: str, review_version_id: str) -> None:
        """Replace only the review version. The issued snapshot stays."""

    def commit_confirmation(self, record: Confirmation) -> Confirmation | Err:
        """Re-check the key, the answer, the review version, and the slot, then write.

        Those steps happen together. Two callers cannot both become the official
        record for one paper, sub-question, and review version.
        """
