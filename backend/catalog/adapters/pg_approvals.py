"""PostgreSQL approval snapshots. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from psycopg.errors import UniqueViolation
from psycopg.types.json import Json

from backend.catalog.adapters.pg_answers import insert_approved_answer
from backend.catalog.adapters.pg_questions import insert_approved_question
from backend.catalog.domain.formula_parts import option_from_json, option_json, stem_from_json, stem_json
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.catalog.domain.validate import TYPE_STRUCTURE
from backend.kernel.result import StoreFault

T = TypeVar("T")

_COLUMNS = """
question_version_id, answer_version_id, asset_ids, layout_template_id,
question_approved, answer_approved, retired, subject_id, item_order, stem, answer_text,
type, structure, option_text, answer_space, stem_parts, option_parts,
book_id, pdf_page
"""


class PgApprovals:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def put(self, snapshot: ApprovalSnapshot) -> None:
        _run(self._pool, lambda conn: _save(conn, snapshot))

    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        return _run(self._pool, lambda conn: _read(conn, question_version_id))

    def list_snapshots(self) -> tuple[ApprovalSnapshot, ...]:
        return _run(self._pool, _list)

    def require_snapshot(self, question_version_id: str) -> ApprovalSnapshot:
        found = self.read_snapshot(question_version_id)
        if found is None:
            raise StoreFault("snapshot_not_found")
        return found

    def has_version_id(self, version_id: str) -> bool:
        statement = """
            SELECT 1 FROM approvals
            WHERE question_version_id = %s OR answer_version_id = %s
            LIMIT 1
        """
        return _run(self._pool, lambda conn: _exists(conn, statement, (version_id, version_id)))

    def set_answer_space(self, question_version_id: str, space: str | None) -> None:
        """Update only the answer-space column. Issued papers keep their boxes."""
        _run(
            self._pool,
            lambda conn: conn.execute(
                "UPDATE approvals SET answer_space = %s WHERE question_version_id = %s",
                (space, question_version_id),
            ),
        )

    def insert_if_absent(self, snapshot: ApprovalSnapshot) -> bool:
        try:
            return _run(self._pool, lambda conn: _insert_new(conn, snapshot))
        except UniqueViolation:
            return False

    def replace_if_current(self, expected: ApprovalSnapshot, updated: ApprovalSnapshot) -> bool:
        if updated.question_version_id != expected.question_version_id:
            return False
        return _run(self._pool, lambda conn: _replace(conn, expected, updated))


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _upsert(conn: Any, snapshot: ApprovalSnapshot) -> None:
    assignments = """
        answer_version_id = EXCLUDED.answer_version_id,
        asset_ids = EXCLUDED.asset_ids,
        layout_template_id = EXCLUDED.layout_template_id,
        question_approved = EXCLUDED.question_approved,
        answer_approved = EXCLUDED.answer_approved,
        retired = EXCLUDED.retired,
        subject_id = EXCLUDED.subject_id,
        item_order = EXCLUDED.item_order,
        stem = EXCLUDED.stem,
        answer_text = EXCLUDED.answer_text,
        type = EXCLUDED.type,
        structure = EXCLUDED.structure,
        option_text = EXCLUDED.option_text,
        answer_space = EXCLUDED.answer_space,
        stem_parts = EXCLUDED.stem_parts,
        option_parts = EXCLUDED.option_parts,
        book_id = EXCLUDED.book_id,
        pdf_page = EXCLUDED.pdf_page
    """
    conn.execute(
        f"""
        INSERT INTO approvals ({_COLUMNS}) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (question_version_id) DO UPDATE SET {assignments}
        """,
        _params(snapshot),
    )


def _insert_new(conn: Any, snapshot: ApprovalSnapshot) -> bool:
    if _exists(
        conn,
        """
        SELECT 1 FROM approvals
        WHERE question_version_id = %s OR answer_version_id = %s
        LIMIT 1
        """,
        (snapshot.question_version_id, snapshot.answer_version_id),
    ):
        return False
    conn.execute(
        f"""
        INSERT INTO approvals ({_COLUMNS}) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        _params(snapshot),
    )
    _remember(conn, snapshot)
    return True


def _save(conn: Any, snapshot: ApprovalSnapshot) -> None:
    _upsert(conn, snapshot)
    _remember(conn, snapshot)


def _replace(conn: Any, expected: ApprovalSnapshot, updated: ApprovalSnapshot) -> bool:
    current = _read_locked(conn, expected.question_version_id)
    if current != expected:
        return False
    _upsert(conn, updated)
    _remember(conn, updated)
    return True


def _remember(conn: Any, snapshot: ApprovalSnapshot) -> None:
    if not snapshot.question_approved or not snapshot.answer_approved:
        return
    if not insert_approved_question(conn, snapshot):
        return
    insert_approved_answer(conn, snapshot)


def _list(conn: Any) -> tuple[ApprovalSnapshot, ...]:
    rows = conn.execute(f"SELECT {_COLUMNS} FROM approvals ORDER BY question_version_id").fetchall()
    return tuple(_snapshot(row) for row in rows)


def _read(conn: Any, question_version_id: str) -> ApprovalSnapshot | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM approvals WHERE question_version_id = %s",
        (question_version_id,),
    ).fetchone()
    if row is None:
        return None
    return _snapshot(row)


def _read_locked(conn: Any, question_version_id: str) -> ApprovalSnapshot | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM approvals WHERE question_version_id = %s FOR UPDATE",
        (question_version_id,),
    ).fetchone()
    if row is None:
        return None
    return _snapshot(row)


def _exists(conn: Any, statement: str, params: tuple[object, ...]) -> bool:
    return conn.execute(statement, params).fetchone() is not None


def _params(snapshot: ApprovalSnapshot) -> tuple[object, ...]:
    return (
        snapshot.question_version_id,
        snapshot.answer_version_id,
        list(snapshot.asset_ids),
        snapshot.layout_template_id,
        snapshot.question_approved,
        snapshot.answer_approved,
        snapshot.retired,
        snapshot.subject_id,
        list(snapshot.item_order),
        snapshot.stem,
        snapshot.answer_text,
        *_stored_type(snapshot),
        "\n".join(snapshot.options),
        snapshot.answer_space,
        _json_or_null(stem_json(snapshot.stem_parts)),
        _json_or_null(option_json(snapshot.option_parts)),
        snapshot.book_id,
        snapshot.pdf_page,
    )


def _snapshot(row: tuple[object, ...]) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=str(row[0]),
        answer_version_id=str(row[1]),
        asset_ids=_texts(row[2]),
        layout_template_id=str(row[3]),
        question_approved=bool(row[4]),
        answer_approved=bool(row[5]),
        retired=bool(row[6]),
        subject_id=str(row[7]),
        item_order=_texts(row[8]),
        stem=str(row[9]),
        answer_text=str(row[10]),
        type="" if row[11] is None else str(row[11]),
        structure="" if row[12] is None else str(row[12]),
        options=_option_lines(row[13]),
        answer_space=None if row[14] is None else str(row[14]),
        stem_parts=stem_from_json(row[15]) if len(row) > 15 else None,
        option_parts=option_from_json(row[16]) if len(row) > 16 else None,
        book_id=None if len(row) <= 17 or row[17] is None else str(row[17]),
        pdf_page=None if len(row) <= 18 or row[18] is None else int(row[18]),
    )


def _stored_type(snapshot: ApprovalSnapshot) -> tuple[str | None, str | None]:
    if TYPE_STRUCTURE.get(snapshot.type) != snapshot.structure or snapshot.type == "":
        return None, None
    return snapshot.type, snapshot.structure


def _json_or_null(value: object) -> object:
    """None stays SQL NULL. An empty list is a real structured value."""
    if value is None:
        return None
    return Json(value)


def _option_lines(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(line for line in str(value).split("\n") if line)


def _texts(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)  # type: ignore[union-attr]
