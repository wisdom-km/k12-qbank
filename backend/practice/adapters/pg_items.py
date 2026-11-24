"""PostgreSQL practice_item rows. SQL stays in this file."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from backend.practice.domain.item import ItemBox, PracticeItem, stored_item
from backend.practice.domain.page_face import formula_from_stem
from backend.practice.domain.paper import Paper

T = TypeVar("T")

_PAPER = """
paper_id, teacher_id, student_id, subject_id, question_version_id, answer_version_id,
asset_ids, layout_template_id, review_version_id, file_id, status, item_order, file_checksum, formula,
qr_printed, printed_external_id, slots_per_page, layout_kind, layout_params, issued_on
"""


class PgPracticeItems:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def items_of(self, paper_id: str) -> tuple[PracticeItem, ...]:
        return _run(self._pool, lambda conn: _items(conn, paper_id))

    def set_items(self, paper_id: str, items: Sequence[PracticeItem]) -> None:
        """Replace every item of this paper in one transaction. Empty deletes them."""
        stored = tuple(stored_item(paper_id, item) for item in items)
        _run(self._pool, lambda conn: _replace_items(conn, paper_id, stored))

    def place_composed(self, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
        """Insert the paper, its pages, and the item rows together."""
        stored = tuple(stored_item(paper.paper_id, item) for item in items)

        def work(conn: Any) -> None:
            _insert_paper(conn, paper)
            _insert_pages(conn, paper, stored)
            _replace_items(conn, paper.paper_id, stored)

        _run(self._pool, work)


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _items(conn: Any, paper_id: str) -> tuple[PracticeItem, ...]:
    rows = conn.execute(
        """
        SELECT paper_id, order_no, question_version_id, answer_version_id, score,
               stem_text, answer_text, page_no, slot_no, slot_span, option_text, placed_lines
        FROM practice_item
        WHERE paper_id = %s
        ORDER BY order_no ASC
        """,
        (paper_id,),
    ).fetchall()
    boxes = _boxes(conn, paper_id)
    return tuple(_item(row, boxes.get(int(row[1]), ())) for row in rows)


def _replace_items(conn: Any, paper_id: str, items: tuple[PracticeItem, ...]) -> None:
    conn.execute("DELETE FROM practice_item_box WHERE paper_id = %s", (paper_id,))
    conn.execute("DELETE FROM practice_item WHERE paper_id = %s", (paper_id,))
    for item in items:
        conn.execute(
            """
            INSERT INTO practice_item (
                paper_id, order_no, question_version_id, answer_version_id, score,
                stem_text, answer_text, page_no, slot_no, slot_span, option_text, placed_lines
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item.paper_id,
                item.order_no,
                item.question_version_id,
                item.answer_version_id,
                item.score,
                item.stem_text,
                item.answer_text,
                item.page_no,
                item.slot_no,
                item.slot_span,
                item.option_text,
                _dump_lines(item.placed_lines),
            ),
        )
        for box in item.boxes:
            conn.execute(
                """
                INSERT INTO practice_item_box (
                    paper_id, order_no, box_no, page_no, x, y, w, h, kind
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    paper_id,
                    item.order_no,
                    box.box_no,
                    box.page_no,
                    box.x,
                    box.y,
                    box.w,
                    box.h,
                    box.kind,
                ),
            )


def _insert_paper(conn: Any, paper: Paper) -> None:
    conn.execute(
        f"""
        INSERT INTO papers ({_PAPER})
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date)
        """,
        (
            paper.paper_id,
            paper.teacher_id,
            paper.student_id,
            paper.subject_id,
            paper.question_version_id,
            paper.answer_version_id,
            list(paper.asset_ids),
            paper.layout_template_id,
            paper.review_version_id,
            paper.file_id,
            paper.status,
            list(paper.item_order),
            paper.file_checksum,
            paper.formula,
            paper.qr_printed,
            paper.printed_external_id,
            paper.slots_per_page,
            paper.layout_kind,
            paper.layout_params or None,
            paper.issued_on,
        ),
    )


def _insert_pages(conn: Any, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
    """slots_per_page 1 follows the input sequence. 4 follows the packed page_no."""
    if paper.layout_kind == "flow" or paper.slots_per_page > 1:
        _insert_packed_pages(conn, paper, items)
        return
    count = len(items)
    for number, item in enumerate(items, start=1):
        _insert_one_page(conn, paper, item, number, count)


def _insert_packed_pages(conn: Any, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
    grouped: dict[int, PracticeItem] = {}
    for item in items:
        grouped.setdefault(max(item.page_no, 1), item)
    count = max(grouped) if grouped else 1
    for page_no in sorted(grouped):
        item = grouped[page_no]
        _insert_one_page(conn, paper, item, page_no, count)


def _insert_one_page(conn: Any, paper: Paper, item: PracticeItem, number: int, count: int) -> None:
    conn.execute(
        """
        INSERT INTO paper_pages (
            paper_id, page_number, page_count, question_version_id, answer_version_id,
            formula, student_id, item_order, asset_ids, layout_template_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            paper.paper_id,
            number,
            count,
            item.question_version_id,
            item.answer_version_id,
            formula_from_stem(item.stem_text) if item.stem_text else paper.formula,
            paper.student_id,
            list(paper.item_order),
            list(paper.asset_ids),
            paper.layout_template_id,
        ),
    )


def _item(row: tuple[object, ...], boxes: tuple[ItemBox, ...]) -> PracticeItem:
    score = row[4]
    return PracticeItem(
        paper_id=str(row[0]),
        order_no=int(row[1]),  # type: ignore[arg-type]
        question_version_id=str(row[2]),
        answer_version_id=str(row[3]),
        score=None if score is None else int(score),  # type: ignore[arg-type]
        stem_text=str(row[5]),
        answer_text=str(row[6]),
        page_no=int(row[7]),  # type: ignore[arg-type]
        slot_no=int(row[8]),  # type: ignore[arg-type]
        slot_span=int(row[9]),  # type: ignore[arg-type]
        option_text=str(row[10]),
        placed_lines=_load_lines(row[11]),
        boxes=boxes,
    )


def _boxes(conn: Any, paper_id: str) -> dict[int, tuple[ItemBox, ...]]:
    rows = conn.execute(
        """
        SELECT order_no, box_no, page_no, x, y, w, h, kind
        FROM practice_item_box
        WHERE paper_id = %s
        ORDER BY order_no, box_no
        """,
        (paper_id,),
    ).fetchall()
    grouped: dict[int, list[ItemBox]] = {}
    for row in rows:
        grouped.setdefault(int(row[0]), []).append(
            ItemBox(
                box_no=int(row[1]),
                page_no=int(row[2]),
                x=float(row[3]),
                y=float(row[4]),
                w=float(row[5]),
                h=float(row[6]),
                kind=str(row[7]),
            )
        )
    return {order: tuple(items) for order, items in grouped.items()}


def _dump_lines(lines: tuple[tuple[str, float, float], ...]) -> str | None:
    if not lines:
        return None
    return json.dumps([[text, x, y] for text, x, y in lines], ensure_ascii=False)


def _load_lines(value: object) -> tuple[tuple[str, float, float], ...]:
    if not value:
        return ()
    raw = json.loads(str(value))
    return tuple((str(row[0]), float(row[1]), float(row[2])) for row in raw)
