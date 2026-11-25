"""PostgreSQL book and lesson rows. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from backend.catalog.domain.book_lesson import BookLesson

T = TypeVar("T")


class PgBooks:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def remember(self, book_id: str, subject_id: str) -> None:
        _run(self._pool, lambda conn: _remember(conn, book_id, subject_id))

    def replace_lessons(self, book_id: str, subject_id: str, lessons: tuple[BookLesson, ...]) -> None:
        _run(self._pool, lambda conn: _replace(conn, book_id, subject_id, lessons))

    def lessons_of(self, book_id: str) -> tuple[BookLesson, ...]:
        return _run(self._pool, lambda conn: _lessons(conn, book_id))

    def has_book(self, book_id: str) -> bool:
        return _run(self._pool, lambda conn: _has(conn, book_id))


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _remember(conn: Any, book_id: str, subject_id: str) -> None:
    conn.execute(
        """
        INSERT INTO book (book_id, subject_id, imported_at)
        VALUES (%s, %s, now())
        ON CONFLICT (book_id) DO NOTHING
        """,
        (book_id, subject_id),
    )


def _replace(conn: Any, book_id: str, subject_id: str, lessons: tuple[BookLesson, ...]) -> None:
    _remember(conn, book_id, subject_id)
    conn.execute("DELETE FROM book_lesson WHERE book_id = %s", (book_id,))
    for lesson in lessons:
        conn.execute(
            """
            INSERT INTO book_lesson (
                book_id, chapter_order, chapter_title, section_title,
                lesson_order, lesson_title, start_page, end_page
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                book_id,
                lesson.chapter_order,
                lesson.chapter_title,
                lesson.section_title,
                lesson.lesson_order,
                lesson.lesson_title,
                lesson.start_page,
                lesson.end_page,
            ),
        )


def _lessons(conn: Any, book_id: str) -> tuple[BookLesson, ...]:
    rows = conn.execute(
        """
        SELECT chapter_order, chapter_title, section_title, lesson_order, lesson_title, start_page, end_page
        FROM book_lesson
        WHERE book_id = %s
        ORDER BY lesson_order
        """,
        (book_id,),
    ).fetchall()
    return tuple(
        BookLesson(
            chapter_order=int(row[0]),
            chapter_title=str(row[1]),
            section_title=None if row[2] is None else str(row[2]),
            lesson_order=int(row[3]),
            lesson_title=str(row[4]),
            start_page=int(row[5]),
            end_page=int(row[6]),
        )
        for row in rows
    )


def _has(conn: Any, book_id: str) -> bool:
    return conn.execute("SELECT 1 FROM book WHERE book_id = %s", (book_id,)).fetchone() is not None
