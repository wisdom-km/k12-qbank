"""In-memory answer drafts. The same records are what PostgreSQL will insert."""

from __future__ import annotations

import threading

from backend.catalog.domain.answer import AnswerDraft


class MemoryAnswers:
    def __init__(self) -> None:
        self._items: dict[str, AnswerDraft] = {}
        self._open: dict[str, str] = {}
        self._lock = threading.Lock()

    def put(self, answer: AnswerDraft) -> str | None:
        """Store one answer. Return the other key when a second applicable row is refused."""
        with self._lock:
            if answer.applicable:
                current = self._open.get(answer.question_key)
                if current is not None and current != answer.key:
                    return current
            previous = self._items.get(answer.key)
            self._items[answer.key] = answer
            if (
                previous is not None
                and previous.applicable
                and self._open.get(previous.question_key) == previous.key
                and not (answer.applicable and answer.question_key == previous.question_key)
            ):
                self._open.pop(previous.question_key, None)
            if answer.applicable:
                self._open[answer.question_key] = answer.key
            return None

    def read(self, key: str) -> AnswerDraft | None:
        with self._lock:
            return self._items.get(key)
