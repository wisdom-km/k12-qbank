"""Catalog lesson tree. Issuable means approved, not retired, and no formula problem."""

from __future__ import annotations

from backend.catalog.application.book_toc import lesson_order_for
from backend.catalog.domain.book_lesson import BookLesson
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.practice.api import unsupported_commands


def placement(snapshot: ApprovalSnapshot, lessons: tuple[BookLesson, ...]) -> dict[str, object]:
    page = 0 if snapshot.pdf_page is None else snapshot.pdf_page
    book_id = snapshot.book_id or ""
    if not book_id or snapshot.pdf_page is None:
        return _blank(book_id, page)
    order = lesson_order_for(snapshot.pdf_page, lessons)
    if order is None:
        return _blank(book_id, page)
    lesson = next(item for item in lessons if item.lesson_order == order)
    return {
        "book_id": book_id,
        "chapter_title": lesson.chapter_title,
        "section_title": lesson.section_title or "",
        "lesson_title": lesson.lesson_title,
        "lesson_order": lesson.lesson_order,
        "pdf_page": page,
    }


def lesson_tree(book_id: str, lessons: tuple[BookLesson, ...], snapshots: tuple[ApprovalSnapshot, ...]) -> dict[str, object]:
    counts: dict[int, int] = {}
    for snapshot in snapshots:
        if snapshot.book_id != book_id or snapshot.pdf_page is None:
            continue
        if not issuable(snapshot):
            continue
        order = lesson_order_for(snapshot.pdf_page, lessons)
        if order is None:
            continue
        counts[order] = counts.get(order, 0) + 1
    chapters: list[dict[str, object]] = []
    for lesson in lessons:
        chapter = _bucket(chapters, lesson.chapter_order, lesson.chapter_title)
        sections = chapter["sections"]
        assert isinstance(sections, list)
        section = _section(sections, lesson.section_title or "")
        rows = section["lessons"]
        assert isinstance(rows, list)
        rows.append(
            {
                "order": lesson.lesson_order,
                "title": lesson.lesson_title,
                "start_page": lesson.start_page,
                "end_page": lesson.end_page,
                "issuable_count": counts.get(lesson.lesson_order, 0),
            }
        )
    return {"book_id": book_id, "chapters": chapters}


def issuable(snapshot: ApprovalSnapshot) -> bool:
    if not snapshot.question_approved or not snapshot.answer_approved or snapshot.retired:
        return False
    if snapshot.stem_parts is None:
        return False
    return not _formula_problem(snapshot)


def _formula_problem(snapshot: ApprovalSnapshot) -> bool:
    for kind, value in snapshot.stem_parts or ():
        if kind == "math" and unsupported_commands(value):
            return True
    for _key, parts in snapshot.option_parts or ():
        for kind, value in parts:
            if kind == "math" and unsupported_commands(value):
                return True
    return False


def _blank(book_id: str, page: int) -> dict[str, object]:
    return {
        "book_id": book_id,
        "chapter_title": "",
        "section_title": "",
        "lesson_title": "",
        "lesson_order": 0,
        "pdf_page": page,
    }


def _bucket(chapters: list[dict[str, object]], order: int, title: str) -> dict[str, object]:
    for chapter in chapters:
        if chapter["order"] == order:
            return chapter
    chapter = {"order": order, "title": title, "sections": []}
    chapters.append(chapter)
    return chapter


def _section(sections: list[dict[str, object]], title: str) -> dict[str, object]:
    for section in sections:
        if section["title"] == title:
            return section
    section = {"title": title, "lessons": []}
    sections.append(section)
    return section
