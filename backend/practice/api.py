"""Public practice types. Other slices import this module and nothing under it."""

from __future__ import annotations

from dataclasses import dataclass

from backend.practice.domain.confirm import Confirmation
from backend.practice.domain.paper import Paper

__all__ = ["ConfirmCommand", "Confirmation", "IssuePaperCommand", "Paper"]


@dataclass(frozen=True)
class IssuePaperCommand:
    teacher_id: str
    student_id: str
    subject_id: str
    question_version_id: str
    review_version_id: str


@dataclass(frozen=True)
class ConfirmCommand:
    operation_key: str
    paper_id: str
    sub_question_id: str
    teacher_id: str
    review_version_id: str
    decision: str
    fixture_answer_id: str
