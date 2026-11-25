"""Parse a catalog page into chapters, sections, and lessons. The text stays out of the report."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.catalog.domain.book_lesson import BookLesson, lesson_identity

_CHAPTER = re.compile(r"^##\s*(?P<title>.+?)\s*$")
_H1 = re.compile(r"^#(?!#)")
_LESSON = re.compile(r"^(?P<title>.+?)(?:\u2026+|\.{3,})\s*(?P<page>\d+)\s*$")
_TOC_KEYS = {"pdf_page", "text"}


@dataclass(frozen=True)
class TocLine:
    pdf_page: int
    line: int


@dataclass(frozen=True)
class TocResult:
    chapters: int
    sections: int
    lessons: tuple[BookLesson, ...]
    unparsed: tuple[TocLine, ...]


def parse_toc(raw: object, offset: object, last_question_page: int) -> tuple[TocResult | None, str]:
    """Return no document when the request omits a catalog. A reason rejects the book."""
    if raw is None or raw == []:
        return None, ""
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        return None, "unknown_field"
    if not isinstance(raw, list):
        return None, "unknown_field"
    pages: list[tuple[int, str]] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - _TOC_KEYS:
            return None, "unknown_field"
        number = item.get("pdf_page")
        text = item.get("text")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1 or not isinstance(text, str):
            return None, "unknown_field"
        pages.append((number, text))
    pages.sort(key=lambda item: item[0])
    return _parse_pages(pages, offset, last_question_page), ""


def lessons_changed(stored: tuple[BookLesson, ...], new: tuple[BookLesson, ...]) -> bool:
    """A first catalog is not a change. Spacing and full-width parentheses do not count."""
    if not stored:
        return False
    return tuple(lesson_identity(item) for item in stored) != tuple(lesson_identity(item) for item in new)


def lesson_order_for(page: int, lessons: tuple[BookLesson, ...]) -> int | None:
    for lesson in lessons:
        if lesson.start_page <= page <= lesson.end_page:
            return lesson.lesson_order
    return None


def _parse_pages(pages: list[tuple[int, str]], offset: int, last_question_page: int) -> TocResult:
    chapter_order = 0
    chapter_title = ""
    section_title: str | None = None
    sections = 0
    pending: list[tuple[int, str, str | None, str, int]] = []
    unparsed: list[TocLine] = []
    for pdf_page, text in pages:
        for index, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or _H1.match(line):
                continue
            if "参考答案" in line:
                continue
            chapter = _CHAPTER.match(line)
            if chapter:
                chapter_order += 1
                chapter_title = chapter.group("title").strip()
                section_title = None
                continue
            lesson = _LESSON.match(line)
            if lesson and chapter_order:
                printed = int(lesson.group("page"))
                title = lesson.group("title").strip()
                start = printed + offset
                if printed < 1 or start < 1 or not title:
                    unparsed.append(TocLine(pdf_page, index))
                    continue
                pending.append((chapter_order, chapter_title, section_title, title, start))
                continue
            if chapter_order and not re.search(r"\d\s*$", line):
                section_title = line
                sections += 1
                continue
            unparsed.append(TocLine(pdf_page, index))
    lessons = _with_ends(pending, last_question_page)
    return TocResult(chapter_order, sections, lessons, tuple(unparsed))


def _with_ends(
    pending: list[tuple[int, str, str | None, str, int]],
    last_question_page: int,
) -> tuple[BookLesson, ...]:
    rows: list[BookLesson] = []
    for index, (chapter_order, chapter_title, section_title, title, start) in enumerate(pending, start=1):
        if index < len(pending):
            end = pending[index][4] - 1
            if end < start:
                end = start
        else:
            end = start if last_question_page < start else last_question_page
        rows.append(
            BookLesson(
                chapter_order=chapter_order,
                chapter_title=chapter_title,
                section_title=section_title,
                lesson_order=index,
                lesson_title=title,
                start_page=start,
                end_page=end,
            )
        )
    return tuple(rows)
