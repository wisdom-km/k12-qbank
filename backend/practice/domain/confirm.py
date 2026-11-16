"""R3 and R5: only a teacher confirmation is official.

Idempotency is the student paper, the sub-question, the server teacher, and the key.
The same scope and the same content returns the original confirmation.
The same scope and different content is refused.
The review version is checked separately. One review slot still holds one official record.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.kernel.result import Err
from backend.practice.domain.paper import Paper


@dataclass(frozen=True)
class OperationKey:
    """One confirmation's idempotency key. The review version is not inside it."""

    value: str


def parse_operation_key(raw: str) -> OperationKey | Err:
    if not raw.strip():
        return Err("empty_operation_key", "the operation key is required")
    return OperationKey(raw)


@dataclass(frozen=True)
class ConfirmationScope:
    """Where one operation key is idempotent.

    The same key string on another paper, sub-question, or server teacher is a
    different confirmation. The review version stays outside this scope.
    """

    paper_id: str
    sub_question_id: str
    teacher_id: str
    operation_key: OperationKey


def scope_of(record: Confirmation) -> ConfirmationScope:
    return ConfirmationScope(
        record.paper_id,
        record.sub_question_id,
        record.teacher_id,
        record.operation_key,
    )


@dataclass(frozen=True)
class Confirmation:
    confirmation_id: str
    operation_key: OperationKey
    paper_id: str
    sub_question_id: str
    teacher_id: str
    review_version_id: str
    decision: str
    fixture_answer_id: str


@dataclass(frozen=True)
class PendingAnswer:
    """One synthetic answer waiting for a teacher. The server loads this row."""

    fixture_answer_id: str
    paper_id: str
    sub_question_id: str
    review_version_id: str
    student_id: str
    status: str


OFFICIAL_DECISIONS = frozenset({"adopt", "revise", "reject"})


def parse_decision(raw: str) -> str | Err:
    """A teacher conclusion is adopt, revise, or reject. Anything else is refused."""
    if raw not in OFFICIAL_DECISIONS:
        return Err("invalid_decision", "the teacher decision must be adopt, revise, or reject")
    return raw


def same_content(existing: Confirmation, record: Confirmation) -> bool:
    return (
        existing.operation_key == record.operation_key
        and existing.paper_id == record.paper_id
        and existing.sub_question_id == record.sub_question_id
        and existing.teacher_id == record.teacher_id
        and existing.review_version_id == record.review_version_id
        and existing.decision == record.decision
        and existing.fixture_answer_id == record.fixture_answer_id
    )


def classify_operation(existing: Confirmation | None, record: Confirmation) -> str:
    """Return absent, replay, or mismatch."""
    if existing is None:
        return "absent"
    if same_content(existing, record):
        return "replay"
    return "mismatch"


def answer_association(
    answer: PendingAnswer | None,
    *,
    paper: Paper,
    sub_question_id: str,
    review_version_id: str,
    claimed_answer_id: str,
) -> Err | None:
    """The loaded answer must belong to this paper, sub-question, review, and student.

    An unknown id, another paper, another sub-question, or a row that is not
    waiting is refused. Nothing is guessed.
    """
    if (
        answer is None
        or answer.status != "pending"
        or answer.paper_id != paper.paper_id
        or answer.sub_question_id != sub_question_id
        or answer.review_version_id != review_version_id
        or answer.fixture_answer_id != claimed_answer_id
        or answer.student_id != paper.student_id
    ):
        return Err(
            "answer_not_owned",
            "the answer is not bound to this student paper and sub-question",
        )
    return None


def decide_commit(
    *,
    paper: Paper | None,
    existing: Confirmation | None,
    answer: PendingAnswer | None,
    slot_taken: bool,
    record: Confirmation,
) -> Confirmation | Err:
    """Pick the one official row for this key and review slot.

    A stored same-content key is returned before the review version is checked,
    so a later version change does not rewrite that confirmation. The first
    write re-reads the paper's review version and the pending answer together.
    """
    if existing is not None:
        if same_content(existing, record):
            return existing
        return Err(
            "key_content_mismatch",
            "the same operation key was sent with different content",
        )
    if paper is None:
        return Err("not_found", "the student paper does not exist")
    owned = answer_association(
        answer,
        paper=paper,
        sub_question_id=record.sub_question_id,
        review_version_id=record.review_version_id,
        claimed_answer_id=record.fixture_answer_id,
    )
    if owned is not None:
        return owned
    if record.review_version_id != paper.review_version_id:
        return Err("version_mismatch", "the review version changed")
    if slot_taken:
        return Err(
            "confirm_conflict",
            "another confirmation already holds this review version",
        )
    return record
