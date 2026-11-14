"""In-memory papers and confirmations. Replacing a review version keeps the issued snapshot."""

from __future__ import annotations

from backend.practice.domain.confirm import Confirmation
from backend.practice.domain.paper import Paper


class MemoryAuth:
    def __init__(self) -> None:
        self._allowed: set[tuple[str, str, str]] = set()

    def grant(self, teacher_id: str, student_id: str, subject_id: str) -> None:
        self._allowed.add((teacher_id, student_id, subject_id))

    def allow(self, teacher_id: str, student_id: str, subject_id: str) -> bool:
        return (teacher_id, student_id, subject_id) in self._allowed


class MemoryPractice:
    def __init__(self) -> None:
        self._papers: dict[str, Paper] = {}
        self._by_key: dict[str, Confirmation] = {}
        self._slots: dict[tuple[str, str, str], str] = {}

    def add_paper(self, paper: Paper) -> None:
        self._papers[paper.paper_id] = paper

    def get_paper(self, paper_id: str) -> Paper | None:
        return self._papers.get(paper_id)

    def paper_count(self) -> int:
        return len(self._papers)

    def set_review_version(self, paper_id: str, review_version_id: str) -> None:
        current = self._papers[paper_id]
        self._papers[paper_id] = Paper(
            paper_id=current.paper_id,
            teacher_id=current.teacher_id,
            student_id=current.student_id,
            subject_id=current.subject_id,
            question_version_id=current.question_version_id,
            answer_version_id=current.answer_version_id,
            asset_ids=current.asset_ids,
            layout_template_id=current.layout_template_id,
            review_version_id=review_version_id,
            file_id=current.file_id,
            status=current.status,
        )

    def get_confirmation(self, operation_key: str) -> Confirmation | None:
        return self._by_key.get(operation_key)

    def find_slot(self, paper_id: str, sub_question_id: str, review_version_id: str) -> str | None:
        return self._slots.get((paper_id, sub_question_id, review_version_id))

    def add_confirmation(self, record: Confirmation) -> None:
        self._by_key[record.operation_key] = record
        slot = (record.paper_id, record.sub_question_id, record.review_version_id)
        self._slots[slot] = record.operation_key

    def confirmation_count(self) -> int:
        return len(self._by_key)
