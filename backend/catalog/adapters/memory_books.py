"""In-memory book and lesson rows for tests and the memory server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.catalog.domain.book_lesson import BookLesson


@dataclass
class _Book:
    subject_id: str
    imported_at: datetime
    lessons: tuple[BookLesson, ...]


class MemoryBooks:
    def __init__(self) -> None:
        self._books: dict[str, _Book] = {}

    def remember(self, book_id: str, subject_id: str) -> None:
        current = self._books.get(book_id)
        if current is None:
            self._books[book_id] = _Book(subject_id, datetime.now(timezone.utc), ())
            return
        current.subject_id = subject_id

    def replace_lessons(self, book_id: str, subject_id: str, lessons: tuple[BookLesson, ...]) -> None:
        self.remember(book_id, subject_id)
        current = self._books[book_id]
        current.lessons = lessons

    def lessons_of(self, book_id: str) -> tuple[BookLesson, ...]:
        current = self._books.get(book_id)
        if current is None:
            return ()
        return current.lessons

    def has_book(self, book_id: str) -> bool:
        return book_id in self._books
