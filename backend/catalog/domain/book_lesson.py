"""One lesson row. The title is display text. Comparison folds spaces and parentheses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookLesson:
    chapter_order: int
    chapter_title: str
    section_title: str | None
    lesson_order: int
    lesson_title: str
    start_page: int
    end_page: int


def fold_title(value: str) -> str:
    """Drop spaces and treat full-width parentheses as half-width."""
    return value.replace(" ", "").replace("\u3000", "").replace("（", "(").replace("）", ")")


def lesson_identity(lesson: BookLesson) -> tuple[object, ...]:
    return (
        lesson.chapter_order,
        fold_title(lesson.chapter_title),
        fold_title(lesson.section_title or ""),
        lesson.lesson_order,
        fold_title(lesson.lesson_title),
        lesson.start_page,
        lesson.end_page,
    )
