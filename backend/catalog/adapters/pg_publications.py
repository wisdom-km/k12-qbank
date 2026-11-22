"""PostgreSQL publication rows. SQL stays in this file. layout_template_id is not read or written."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from backend.catalog.domain.publication import Publication, require_actor

T = TypeVar("T")

_COLUMNS = "publication_id, question_version_id, answer_version_id, subject_id, status"


class PgPublications:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def put(self, publication: Publication) -> None:
        _run(self._pool, lambda conn: _insert(conn, publication))

    def active_of(self, question_version_id: str, answer_version_id: str) -> Publication | None:
        return _run(self._pool, lambda conn: _one(conn, question_version_id, answer_version_id))

    def list_active(self) -> tuple[Publication, ...]:
        return _run(self._pool, _all_active)

    def rows_for(self, question_version_id: str, answer_version_id: str) -> tuple[Publication, ...]:
        return _run(self._pool, lambda conn: _rows(conn, question_version_id, answer_version_id))

    def retire_by_binding(self, q_vid: str, a_vid: str, actor: str | None) -> str:
        require_actor(actor)
        return _run(self._pool, lambda conn: _retire(conn, q_vid, a_vid))


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _insert(conn: Any, publication: Publication) -> None:
    conn.execute(
        f"""
        INSERT INTO publication ({_COLUMNS})
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            publication.publication_id,
            publication.question_version_id,
            publication.answer_version_id,
            publication.subject_id,
            publication.status,
        ),
    )


def _one(conn: Any, question_version_id: str, answer_version_id: str) -> Publication | None:
    row = conn.execute(
        f"""
        SELECT {_COLUMNS}
        FROM publication
        WHERE question_version_id = %s
          AND answer_version_id = %s
          AND status = 'active'
        """,
        (question_version_id, answer_version_id),
    ).fetchone()
    if row is None:
        return None
    return _publication(row)


def _rows(conn: Any, question_version_id: str, answer_version_id: str) -> tuple[Publication, ...]:
    rows = conn.execute(
        f"""
        SELECT {_COLUMNS}
        FROM publication
        WHERE question_version_id = %s
          AND answer_version_id = %s
        ORDER BY publication_id
        """,
        (question_version_id, answer_version_id),
    ).fetchall()
    return tuple(_publication(row) for row in rows)


def _retire(conn: Any, q_vid: str, a_vid: str) -> str:
    updated = conn.execute(
        """
        UPDATE publication
        SET status = 'retired'
        WHERE question_version_id = %s
          AND answer_version_id = %s
          AND status = 'active'
        """,
        (q_vid, a_vid),
    )
    if int(updated.rowcount) == 1:
        return "retired"
    found = conn.execute(
        """
        SELECT 1
        FROM publication
        WHERE question_version_id = %s
          AND answer_version_id = %s
          AND status = 'retired'
        LIMIT 1
        """,
        (q_vid, a_vid),
    ).fetchone()
    if found is not None:
        return "already_retired"
    return "not_found"


def _all_active(conn: Any) -> tuple[Publication, ...]:
    rows = conn.execute(
        f"""
        SELECT {_COLUMNS}
        FROM publication
        WHERE status = 'active'
        ORDER BY publication_id
        """
    ).fetchall()
    return tuple(_publication(row) for row in rows)


def _publication(row: tuple[object, ...]) -> Publication:
    return Publication(
        publication_id=str(row[0]),
        question_version_id=str(row[1]),
        answer_version_id=str(row[2]),
        subject_id=str(row[3]),
        status=str(row[4]),
    )
