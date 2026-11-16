"""In-memory papers and confirmations. Replacing a review version keeps the issued snapshot."""

from __future__ import annotations

import threading
from dataclasses import replace

from backend.kernel.result import Err
from backend.practice.domain.confirm import (
    Confirmation,
    ConfirmationScope,
    PendingAnswer,
    decide_commit,
    scope_of,
)
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
        self._by_scope: dict[ConfirmationScope, Confirmation] = {}
        self._slots: dict[tuple[str, str, str], ConfirmationScope] = {}
        self._answers: dict[str, PendingAnswer] = {}
        self._commit_lock = threading.Lock()

    def add_paper(self, paper: Paper) -> None:
        with self._commit_lock:
            self._papers[paper.paper_id] = paper

    def get_paper(self, paper_id: str) -> Paper | None:
        with self._commit_lock:
            return self._papers.get(paper_id)

    def paper_count(self) -> int:
        with self._commit_lock:
            return len(self._papers)

    def set_review_version(self, paper_id: str, review_version_id: str) -> None:
        with self._commit_lock:
            current = self._papers[paper_id]
            self._papers[paper_id] = replace(current, review_version_id=review_version_id)

    def get_confirmation(self, scope: ConfirmationScope) -> Confirmation | None:
        with self._commit_lock:
            return self._by_scope.get(scope)

    def find_slot(self, paper_id: str, sub_question_id: str, review_version_id: str) -> ConfirmationScope | None:
        with self._commit_lock:
            return self._slots.get((paper_id, sub_question_id, review_version_id))

    def put_answer(self, answer: PendingAnswer) -> None:
        with self._commit_lock:
            self._answers[answer.fixture_answer_id] = answer

    def commit_confirmation(self, record: Confirmation) -> Confirmation | Err:
        """One lock covers the replay, the answer, the review version, the slot, and the insert."""
        with self._commit_lock:
            paper = self._papers.get(record.paper_id)
            scope = scope_of(record)
            existing = self._by_scope.get(scope)
            answer = self._answers.get(record.fixture_answer_id)
            slot = (record.paper_id, record.sub_question_id, record.review_version_id)
            held = self._slots.get(slot)
            slot_taken = held is not None and held != scope
            placed = decide_commit(
                paper=paper,
                existing=existing,
                answer=answer,
                slot_taken=slot_taken,
                record=record,
            )
            if isinstance(placed, Err):
                return placed
            placed_scope = scope_of(placed)
            if placed_scope not in self._by_scope:
                self._by_scope[placed_scope] = placed
                self._slots[slot] = placed_scope
            return placed

    def confirmation_count(self) -> int:
        with self._commit_lock:
            return len(self._by_scope)
