"""PostgreSQL intake pages. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from psycopg.errors import UniqueViolation

from backend.kernel.result import StoreFault
from backend.practice.domain.intake_page import IntakePage

T = TypeVar("T")


class PgIntake:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def get(self, intake_id: str) -> IntakePage | None:
        return _run(self._pool, lambda conn: _one(conn, "WHERE intake_id = %s", (intake_id,)))

    def current(self, paper_id: str, page_no: int) -> IntakePage | None:
        return _run(
            self._pool,
            lambda conn: _one(
                conn,
                "WHERE paper_id = %s AND page_no = %s AND superseded_at IS NULL",
                (paper_id, page_no),
            ),
        )

    def currents(self, paper_id: str) -> tuple[IntakePage, ...]:
        return _run(self._pool, lambda conn: _many(conn, paper_id))

    def file_purpose(self, file_id: str) -> str | None:
        row = _run(
            self._pool,
            lambda conn: conn.execute(
                "SELECT purpose FROM files WHERE file_id = %s",
                (file_id,),
            ).fetchone(),
        )
        if row is None:
            return None
        return str(row[0])

    def count(self) -> int:
        row = _run(self._pool, lambda conn: conn.execute("SELECT count(*) FROM intake_page").fetchone())
        return int(row[0]) if row is not None else 0

    def place(self, row: IntakePage, *, replace: bool) -> None:
        def work(conn: Any) -> None:
            _insert_file(conn, row)
            current = _one(
                conn,
                "WHERE paper_id = %s AND page_no = %s AND superseded_at IS NULL",
                (row.paper_id, row.page_no),
            )
            if current is not None and not replace:
                raise StoreFault("page_already_received")
            if current is not None:
                conn.execute(
                    """
                    UPDATE intake_page
                    SET superseded_at = %s
                    WHERE intake_id = %s AND superseded_at IS NULL
                    """,
                    (row.uploaded_at, current.intake_id),
                )
            try:
                conn.execute(
                    """
                    INSERT INTO intake_page (
                        intake_id, paper_id, page_no, file_id, uploaded_by, uploaded_at, located_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row.intake_id,
                        row.paper_id,
                        row.page_no,
                        row.file_id,
                        row.uploaded_by,
                        row.uploaded_at,
                        row.located_by,
                    ),
                )
            except UniqueViolation as exc:
                if (exc.diag.constraint_name or "") == "intake_page_current":
                    raise StoreFault("page_already_received") from None
                raise

        _run(self._pool, work)


def _insert_file(conn: Any, row: IntakePage) -> None:
    """Insert purpose=intake. An existing row with another purpose is left unchanged."""
    conn.execute(
        """
        INSERT INTO files (file_id, purpose, checksum) VALUES (%s, 'intake', %s)
        ON CONFLICT (file_id) DO NOTHING
        """,
        (row.file_id, row.checksum),
    )
    found = conn.execute("SELECT purpose FROM files WHERE file_id = %s", (row.file_id,)).fetchone()
    if found is None or str(found[0]) != "intake":
        raise StoreFault("file_purpose_conflict")


def _one(conn: Any, where: str, params: tuple[object, ...]) -> IntakePage | None:
    found = conn.execute(
        f"""
        SELECT intake_id, paper_id, page_no, file_id, uploaded_by, uploaded_at, located_by, superseded_at
        FROM intake_page
        {where}
        """,
        params,
    ).fetchone()
    if found is None:
        return None
    checksum = conn.execute("SELECT checksum FROM files WHERE file_id = %s", (found[3],)).fetchone()
    return _row(found, "" if checksum is None else str(checksum[0]))


def _many(conn: Any, paper_id: str) -> tuple[IntakePage, ...]:
    rows = conn.execute(
        """
        SELECT intake.intake_id, intake.paper_id, intake.page_no, intake.file_id,
               intake.uploaded_by, intake.uploaded_at, intake.located_by, intake.superseded_at,
               files.checksum
        FROM intake_page AS intake
        JOIN files ON files.file_id = intake.file_id
        WHERE intake.paper_id = %s AND intake.superseded_at IS NULL
        ORDER BY intake.page_no
        """,
        (paper_id,),
    ).fetchall()
    return tuple(_row(row[:8], str(row[8])) for row in rows)


def _row(row: tuple[object, ...], checksum: str) -> IntakePage:
    return IntakePage(
        intake_id=str(row[0]),
        paper_id=str(row[1]),
        page_no=int(row[2]),  # type: ignore[arg-type]
        file_id=str(row[3]),
        checksum=checksum,
        uploaded_by=str(row[4]),
        uploaded_at=_stamp(row[5]),
        located_by=str(row[6]),
        superseded_at=None if row[7] is None else _stamp(row[7]),
    )


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
