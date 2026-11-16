"""Public practice types. Other slices import this module and nothing under it.

ConfirmCommand.operation_key follows one rule: the same key with the same
content returns the original confirmation, and the same key with different
content is refused. The review version is checked apart from the key.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.practice.domain.confirm import Confirmation, OperationKey
from backend.practice.domain.paper import Paper

__all__ = [
    "AttemptView",
    "ConfirmCommand",
    "Confirmation",
    "IssuePaperCommand",
    "OpenedPaper",
    "OperationKey",
    "Paper",
]


@dataclass(frozen=True)
class IssuePaperCommand:
    teacher_id: str
    student_id: str
    subject_id: str
    question_version_id: str
    review_version_id: str


@dataclass(frozen=True)
class AttemptView:
    """The pending row the page may show. The student number stays on the paper."""

    fixture_answer_id: str
    paper_id: str
    sub_question_id: str
    review_version_id: str
    status: str


@dataclass(frozen=True)
class OpenedPaper:
    """One issued paper. render_code is set when the PDF was not stored."""

    paper: Paper
    fixture_answer_id: str
    render_code: str | None


@dataclass(frozen=True)
class ConfirmCommand:
    """operation_key: same key + same content returns the original; same key + different content is refused."""

    operation_key: str
    paper_id: str
    sub_question_id: str
    teacher_id: str
    review_version_id: str
    decision: str
    fixture_answer_id: str
