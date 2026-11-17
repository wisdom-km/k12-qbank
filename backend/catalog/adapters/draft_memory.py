"""In-memory question drafts. The same records are what PostgreSQL will insert."""

from __future__ import annotations

import threading

from backend.catalog.domain.draft import DraftFile, QuestionDraft


class MemoryDrafts:
    def __init__(self) -> None:
        self._items: dict[str, QuestionDraft] = {}
        self._lock = threading.Lock()

    def save(self, draft: DraftFile) -> None:
        with self._lock:
            for question in draft.questions:
                self._items[question.key] = question

    def read(self, key: str) -> QuestionDraft | None:
        with self._lock:
            return self._items.get(key)
