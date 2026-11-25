"""PostgreSQL teacher decisions. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from backend.practice.domain.decision import TeacherDecision

T = TypeVar("T")

_COLUMNS = """
    decision_id, paper_id, order_no, verdict, source, decided_by, decided_at,
    voided_at, ai_run_id, ai_verdict, ai_confidence, corrected_transcription, comment
"""


class PgDecisions:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def current(self, paper_id: str, order_no: int) -> TeacherDecision | None:
        return _run(
            self._pool,
            lambda conn: _one(
                conn,
                "WHERE paper_id = %s AND order_no = %s AND voided_at IS NULL",
                (paper_id, order_no),
            ),
        )

    def currents(self, paper_id: str) -> tuple[TeacherDecision, ...]:
        return _run(
            self._pool,
            lambda conn: _many(
                conn,
                "WHERE paper_id = %s AND voided_at IS NULL ORDER BY order_no",
                (paper_id,),
            ),
        )

    def history(self, paper_id: str) -> tuple[TeacherDecision, ...]:
        return _run(
            self._pool,
            lambda conn: _many(
                conn,
                "WHERE paper_id = %s ORDER BY order_no, decided_at, decision_id",
                (paper_id,),
            ),
        )

    def replace(self, row: TeacherDecision) -> None:
        def work(conn: Any) -> None:
            conn.execute(
                """
                UPDATE teacher_decision
                SET voided_at = %s
                WHERE paper_id = %s AND order_no = %s AND voided_at IS NULL
                """,
                (row.decided_at, row.paper_id, row.order_no),
            )
            conn.execute(
                f"""
                INSERT INTO teacher_decision ({_COLUMNS})
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
                """,
                (
                    row.decision_id,
                    row.paper_id,
                    row.order_no,
                    row.verdict,
                    row.source,
                    row.decided_by,
                    row.decided_at,
                    _empty(row.ai_run_id),
                    _empty(row.ai_verdict),
                    row.ai_confidence,
                    _empty(row.corrected_transcription),
                    _empty(row.comment),
                ),
            )

        _run(self._pool, work)


def _one(conn: Any, where: str, params: tuple[object, ...]) -> TeacherDecision | None:
    found = conn.execute(f"SELECT {_COLUMNS} FROM teacher_decision {where}", params).fetchone()
    if found is None:
        return None
    return _row(found)


def _many(conn: Any, where: str, params: tuple[object, ...]) -> tuple[TeacherDecision, ...]:
    rows = conn.execute(f"SELECT {_COLUMNS} FROM teacher_decision {where}", params).fetchall()
    return tuple(_row(row) for row in rows)


def _row(row: tuple[object, ...]) -> TeacherDecision:
    return TeacherDecision(
        decision_id=str(row[0]),
        paper_id=str(row[1]),
        order_no=int(row[2]),  # type: ignore[arg-type]
        verdict=str(row[3]),
        source=str(row[4]),
        decided_by=str(row[5]),
        decided_at=_stamp(row[6]),
        voided_at="" if row[7] is None else _stamp(row[7]),
        ai_run_id="" if row[8] is None else str(row[8]),
        ai_verdict="" if row[9] is None else str(row[9]),
        ai_confidence=None if row[10] is None else float(row[10]),  # type: ignore[arg-type]
        corrected_transcription="" if row[11] is None else str(row[11]),
        comment="" if row[12] is None else str(row[12]),
    )


def _empty(value: str) -> str | None:
    text = value.strip()
    return text or None


def _stamp(value: object) -> str:
    iso = getattr(value, "isoformat", None)
    text = iso() if iso is not None else str(value)
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)
