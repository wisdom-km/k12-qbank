"""PostgreSQL approval snapshots. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from psycopg.errors import UniqueViolation

from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.result import StoreFault

T = TypeVar("T")

_COLUMNS = """
question_version_id, answer_version_id, asset_ids, layout_template_id,
question_approved, answer_approved, retired, subject_id, item_order, stem, answer_text
"""


class PgApprovals:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def put(self, snapshot: ApprovalSnapshot) -> None:
        _run(self._pool, lambda conn: _upsert(conn, snapshot))

    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None:
        return _run(self._pool, lambda conn: _read(conn, question_version_id))

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
        answer_text = EXCLUDED.answer_text
    """
    conn.execute(
        f"""
        INSERT INTO approvals ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        f"INSERT INTO approvals ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        _params(snapshot),
    )
    return True


def _replace(conn: Any, expected: ApprovalSnapshot, updated: ApprovalSnapshot) -> bool:
    current = _read_locked(conn, expected.question_version_id)
    if current != expected:
        return False
    _upsert(conn, updated)
    return True


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
    )


def _texts(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)  # type: ignore[union-attr]
