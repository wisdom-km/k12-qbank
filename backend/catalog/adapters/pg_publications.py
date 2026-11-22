"""PostgreSQL publication rows. SQL stays in this file. Explicit publish writes layout_template_id."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from backend.catalog.domain.publication import Publication, clean_layout, require_actor, require_subject

T = TypeVar("T")

_COLUMNS = (
    "publication_id, question_version_id, answer_version_id, "
    "layout_template_id, subject_id, status"
)


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

    def publish_by_binding(
        self,
        question_version_id: str,
        answer_version_id: str,
        actor: str,
        layout_template_id: str | None = None,
    ) -> str:
        require_actor(actor)
        layout = clean_layout(layout_template_id)
        return _run(
            self._pool,
            lambda conn: _publish(conn, question_version_id, answer_version_id, layout),
        )


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _insert(conn: Any, publication: Publication) -> None:
    conn.execute(
        f"""
        INSERT INTO publication ({_COLUMNS})
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            publication.publication_id,
            publication.question_version_id,
            publication.answer_version_id,
            publication.layout_template_id,
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


def _publish(conn: Any, q_vid: str, a_vid: str, layout: str | None) -> str:
    # Two int4 keys. The migration lock is a different bigint key space.
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext('k12.publication.publish'), hashtext(%s))",
        (q_vid + "|" + a_vid,),
    )
    approval = conn.execute(
        """
        SELECT answer_version_id, question_approved, answer_approved, retired, subject_id
        FROM approvals
        WHERE question_version_id = %s
        FOR UPDATE
        """,
        (q_vid,),
    ).fetchone()
    if approval is None or not _approval_allows(approval, a_vid):
        return "not_approved"
    subject = "" if approval[4] is None else str(approval[4])
    require_subject(subject)
    active = conn.execute(
        """
        SELECT 1
        FROM publication
        WHERE question_version_id = %s
          AND answer_version_id = %s
          AND status = 'active'
        """,
        (q_vid, a_vid),
    ).fetchone()
    if active is not None:
        return "already_active"
    counted = conn.execute(
        """
        SELECT COUNT(*)
        FROM publication
        WHERE question_version_id = %s
          AND answer_version_id = %s
        """,
        (q_vid, a_vid),
    ).fetchone()
    seq = int(counted[0]) + 1
    conn.execute(
        """
        INSERT INTO publication (
            publication_id,
            question_version_id,
            answer_version_id,
            layout_template_id,
            subject_id,
            status
        )
        VALUES (%s, %s, %s, %s, %s, 'active')
        """,
        (f"pub-{q_vid}-{a_vid}-{seq}", q_vid, a_vid, layout, subject),
    )
    return "published"


def _approval_allows(approval: tuple[object, ...], answer_version_id: str) -> bool:
    if str(approval[0]) != answer_version_id:
        return False
    if not approval[1] or not approval[2]:
        return False
    return not approval[3]


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
        subject_id=str(row[4]),
        status=str(row[5]),
        layout_template_id=None if row[3] is None else str(row[3]),
    )
