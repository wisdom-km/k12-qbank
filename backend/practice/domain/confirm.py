"""R3 and R5: only a teacher confirmation is official. The same key does not write twice."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    operation_key: str
    paper_id: str
    sub_question_id: str
    teacher_id: str
    review_version_id: str
    decision: str
    fixture_answer_id: str


def same_content(
    existing: Confirmation,
    *,
    operation_key: str,
    paper_id: str,
    sub_question_id: str,
    teacher_id: str,
    review_version_id: str,
    decision: str,
    fixture_answer_id: str,
) -> bool:
    return (
        existing.operation_key == operation_key
        and existing.paper_id == paper_id
        and existing.sub_question_id == sub_question_id
        and existing.teacher_id == teacher_id
        and existing.review_version_id == review_version_id
        and existing.decision == decision
        and existing.fixture_answer_id == fixture_answer_id
    )
