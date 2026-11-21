"""PostgreSQL practice_item rows. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import Paper

T = TypeVar("T")

_PAPER = """
paper_id, teacher_id, student_id, subject_id, question_version_id, answer_version_id,
asset_ids, layout_template_id, review_version_id, file_id, status, item_order, file_checksum, formula
"""


class PgPracticeItems:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def items_of(self, paper_id: str) -> tuple[PracticeItem, ...]:
        return _run(self._pool, lambda conn: _items(conn, paper_id))

    def set_items(self, paper_id: str, items: Sequence[PracticeItem]) -> None:
        """Replace every item of this paper in one transaction. Empty deletes them."""
        stored = tuple(_stored(paper_id, item) for item in items)
        _run(self._pool, lambda conn: _replace_items(conn, paper_id, stored))

    def place_composed(self, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
        """Insert the paper, one page per input item, and the item rows together."""
        stored = tuple(_stored(paper.paper_id, item) for item in items)

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
        SELECT paper_id, order_no, question_version_id, answer_version_id, score
        FROM practice_item
        WHERE paper_id = %s
        ORDER BY order_no ASC
        """,
        (paper_id,),
    ).fetchall()
    return tuple(_item(row) for row in rows)


def _replace_items(conn: Any, paper_id: str, items: tuple[PracticeItem, ...]) -> None:
    conn.execute("DELETE FROM practice_item WHERE paper_id = %s", (paper_id,))
    for item in items:
        conn.execute(
            """
            INSERT INTO practice_item (
                paper_id, order_no, question_version_id, answer_version_id, score
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                item.paper_id,
                item.order_no,
                item.question_version_id,
                item.answer_version_id,
                item.score,
            ),
        )


def _insert_paper(conn: Any, paper: Paper) -> None:
    conn.execute(
        f"""
        INSERT INTO papers ({_PAPER})
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        ),
    )


def _insert_pages(conn: Any, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
    """page_number follows the input sequence. order_no stays on practice_item."""
    count = len(items)
    for number, item in enumerate(items, start=1):
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
                paper.formula,
                paper.student_id,
                list(paper.item_order),
                list(paper.asset_ids),
                paper.layout_template_id,
            ),
        )


def _item(row: tuple[object, ...]) -> PracticeItem:
    score = row[4]
    return PracticeItem(
        paper_id=str(row[0]),
        order_no=int(row[1]),  # type: ignore[arg-type]
        question_version_id=str(row[2]),
        answer_version_id=str(row[3]),
        score=None if score is None else int(score),  # type: ignore[arg-type]
    )


def _stored(paper_id: str, item: PracticeItem) -> PracticeItem:
    return PracticeItem(
        paper_id=paper_id,
        order_no=item.order_no,
        question_version_id=item.question_version_id,
        answer_version_id=item.answer_version_id,
        score=item.score,
    )
