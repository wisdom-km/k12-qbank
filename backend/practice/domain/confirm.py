"""R3 and R5: only a teacher confirmation is official. The same key does not write twice.

Same operation_key and the same content returns the original confirmation.
Same operation_key and different content is refused.
The review version is not part of the key. It is checked separately.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.kernel.result import Err


@dataclass(frozen=True)
class OperationKey:
    """One confirmation's idempotency key. The review version is not inside it."""

    value: str


def parse_operation_key(raw: str) -> OperationKey | Err:
    if not raw.strip():
        return Err("empty_operation_key", "the operation key is required")
    return OperationKey(raw)


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


def classify_operation(
    existing: Confirmation | None,
    *,
    operation_key: str,
    paper_id: str,
    sub_question_id: str,
    teacher_id: str,
    review_version_id: str,
    decision: str,
    fixture_answer_id: str,
) -> str:
    """Return absent, replay, or mismatch.

    Same operation_key and the same content is replay: return the original row.
    Same operation_key and different content is mismatch: refuse, write nothing.
    """
    if existing is None:
        return "absent"
    if same_content(
        existing,
        operation_key=operation_key,
        paper_id=paper_id,
        sub_question_id=sub_question_id,
        teacher_id=teacher_id,
        review_version_id=review_version_id,
        decision=decision,
        fixture_answer_id=fixture_answer_id,
    ):
        return "replay"
    return "mismatch"


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
