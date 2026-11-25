"""Turn imported drafts into unpublished snapshots. An existing version stays."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from backend.catalog.application.answer_text import answer_plain, plain_parts
from backend.catalog.domain.answer import AnswerDraft
from backend.catalog.domain.formula_parts import draft_option_parts, draft_stem_parts
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.catalog.domain.validate import DraftFile, QuestionDraft

_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_SUBJECT = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ReviewWriter(Protocol):
    def insert_if_absent(self, snapshot: ApprovalSnapshot) -> bool:
        """Insert one unpublished version. Return False when an id is already stored."""


@dataclass(frozen=True)
class StagedReview:
    staged: tuple[str, ...]
    kept: tuple[str, ...]
    skipped: tuple[str, ...]


def subject_accepted(subject_id: str) -> bool:
    """Same token rule as a grant subject. The value is not a student number."""
    return bool(_SUBJECT.fullmatch(subject_id))


def stage_review(
    draft: DraftFile,
    answers: tuple[AnswerDraft, ...],
    approvals: ReviewWriter,
    subject_id: str,
    book_id: str = "",
    pages: dict[str, int] | None = None,
) -> StagedReview:
    """Stage one applicable answer per question. Ids come from the draft keys."""
    applicable = {answer.question_key: answer for answer in answers if answer.applicable}
    staged: list[str] = []
    kept: list[str] = []
    skipped: list[str] = []
    for question in draft.questions:
        answer = applicable.get(question.key)
        page = None if pages is None else pages.get(question.key)
        snapshot = None if answer is None else _snapshot(question, answer, subject_id, book_id, page)
        if snapshot is None:
            skipped.append(question.key)
            continue
        if approvals.insert_if_absent(snapshot):
            staged.append(snapshot.question_version_id)
        else:
            kept.append(snapshot.question_version_id)
    return StagedReview(tuple(staged), tuple(kept), tuple(skipped))


def _snapshot(
    question: QuestionDraft,
    answer: AnswerDraft,
    subject_id: str,
    book_id: str = "",
    pdf_page: int | None = None,
) -> ApprovalSnapshot | None:
    question_id = _version_id("qv-", question.key)
    answer_id = _version_id("av-", answer.key)
    if question_id is None or answer_id is None or not subject_id:
        return None
    return ApprovalSnapshot(
        question_version_id=question_id,
        answer_version_id=answer_id,
        asset_ids=(),
        layout_template_id="",
        question_approved=False,
        answer_approved=False,
        retired=False,
        subject_id=subject_id,
        item_order=(question.number,) if question.number else (),
        stem=_plain(question.stem),
        answer_text=answer_plain(answer),
        book_id=book_id or None,
        pdf_page=pdf_page,
        type=question.type,
        structure=question.structure,
        options=tuple(
            f"{option.key}. {_plain(option.content)}".strip() for option in question.options
        ),
        stem_parts=draft_stem_parts(question.stem),
        option_parts=draft_option_parts(question.options),
    )


def _version_id(prefix: str, key: str) -> str | None:
    if not _KEY.fullmatch(key):
        return None
    return prefix + key.replace(":", "-")


def _plain(parts: tuple[object, ...]) -> str:
    """Join text and math from either the question or the answer part types."""
    return plain_parts(parts)
