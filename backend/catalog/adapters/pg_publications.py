"""PostgreSQL publication rows. SQL stays in this file. Explicit publish writes layout_template_id."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from psycopg.errors import UniqueViolation

from backend.catalog.domain.publication import (
    Asset,
    AttachResult,
    Publication,
    RemoveResult,
    RetireCode,
    asset_file_refusal,
    asset_id_for,
    bound_page,
    clean_layout,
    require_actor,
    require_subject,
)

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

    def list_page(
        self,
        question_version_id: str | None = None,
        answer_version_id: str | None = None,
        subject_id: str | None = None,
        status: Literal["active", "retired"] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[tuple[Publication, ...], int]:
        page_offset, page_limit = bound_page(offset, limit)
        return _run(
            self._pool,
            lambda conn: _list_page(
                conn,
                question_version_id,
                answer_version_id,
                subject_id,
                status,
                page_offset,
                page_limit,
            ),
        )

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

    def note_page_file(self, file_id: str) -> None:
        """Test seam. Inserts files.purpose = page so the privacy guard can see it."""
        _run(self._pool, lambda conn: _note_page_file(conn, file_id))

    def note_paper_file(self, file_id: str) -> None:
        """Test seam. Inserts papers.file_id."""
        _run(self._pool, lambda conn: _note_paper(conn, file_id, None, "file-" + file_id))

    def note_paper_checksum(self, checksum: str) -> None:
        """Test seam. Inserts papers.file_checksum. file_id stays null so the file-id guard does not fire."""
        _run(self._pool, lambda conn: _note_paper(conn, None, checksum, "sum-" + checksum))

    def clear_privacy_notes(self) -> None:
        _run(self._pool, _clear_privacy_notes)

    def attach_asset(
        self,
        publication_id: str,
        file_id: str,
        kind: Literal["image", "pdf"],
        checksum: str,
        size_bytes: int,
        mime_type: str,
        actor_id: str,
    ) -> AttachResult:
        require_actor(actor_id)
        return _run(
            self._pool,
            lambda conn: _attach(
                conn,
                publication_id,
                file_id,
                kind,
                checksum,
                size_bytes,
                mime_type,
                actor_id,
            ),
        )

    def remove_asset(self, publication_id: str, publication_asset_id: str, actor_id: str) -> RemoveResult:
        require_actor(actor_id)
        return _run(self._pool, lambda conn: _remove(conn, publication_id, publication_asset_id))

    def list_assets(self, publication_id: str) -> tuple[Asset, ...] | None:
        return _run(self._pool, lambda conn: _list_assets(conn, publication_id))


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
        RETURNING publication_id, subject_id
        """,
        (q_vid, a_vid),
    ).fetchall()
    if len(updated) == 1:
        return RetireCode(
            "retired",
            publication_id=str(updated[0][0]),
            subject_id=str(updated[0][1]),
        )
    if len(updated) > 1:
        raise RuntimeError("more than one active publication matched this binding")
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
        return RetireCode("already_retired")
    return RetireCode("not_found")


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


def _list_page(
    conn: Any,
    question_version_id: str | None,
    answer_version_id: str | None,
    subject_id: str | None,
    status: str | None,
    offset: int,
    limit: int,
) -> tuple[tuple[Publication, ...], int]:
    # Two statements. A window count disappears when OFFSET lands past the last row.
    params = (
        question_version_id,
        question_version_id,
        answer_version_id,
        answer_version_id,
        subject_id,
        subject_id,
        status,
        status,
    )
    counted = conn.execute(
        """
        SELECT COUNT(*)
        FROM publication
        WHERE (%s::text IS NULL OR question_version_id = %s)
          AND (%s::text IS NULL OR answer_version_id = %s)
          AND (%s::text IS NULL OR subject_id = %s)
          AND (%s::text IS NULL OR status = %s)
        """,
        params,
    ).fetchone()
    rows = conn.execute(
        """
        SELECT publication_id, question_version_id, answer_version_id,
               layout_template_id, subject_id, status
        FROM publication
        WHERE (%s::text IS NULL OR question_version_id = %s)
          AND (%s::text IS NULL OR answer_version_id = %s)
          AND (%s::text IS NULL OR subject_id = %s)
          AND (%s::text IS NULL OR status = %s)
        ORDER BY publication_id
        LIMIT %s OFFSET %s
        """,
        params + (limit, offset),
    ).fetchall()
    return tuple(_publication(row) for row in rows), int(counted[0])


def _publication(row: tuple[object, ...]) -> Publication:
    return Publication(
        publication_id=str(row[0]),
        question_version_id=str(row[1]),
        answer_version_id=str(row[2]),
        subject_id=str(row[4]),
        status=str(row[5]),
        layout_template_id=None if row[3] is None else str(row[3]),
    )


def _attach(
    conn: Any,
    publication_id: str,
    file_id: str,
    kind: str,
    checksum: str,
    size_bytes: int,
    mime_type: str,
    actor_id: str,
) -> AttachResult:
    publication = conn.execute(
        """
        SELECT status
        FROM publication
        WHERE publication_id = %s
        """,
        (publication_id,),
    ).fetchone()
    if publication is None:
        return AttachResult("publication_not_found")
    if str(publication[0]) == "retired":
        return AttachResult("publication_retired")
    page_file = conn.execute(
        """
        SELECT 1
        FROM files
        WHERE file_id = %s
          AND purpose = 'page'
        LIMIT 1
        """,
        (file_id,),
    ).fetchone()
    paper_file = conn.execute(
        """
        SELECT 1
        FROM papers
        WHERE file_id = %s
        LIMIT 1
        """,
        (file_id,),
    ).fetchone()
    paper_checksum = conn.execute(
        """
        SELECT 1
        FROM papers
        WHERE file_checksum = %s
        LIMIT 1
        """,
        (checksum,),
    ).fetchone()
    refusal = asset_file_refusal(
        file_id,
        kind,
        mime_type,
        page_file=page_file is not None,
        paper_file=paper_file is not None,
        paper_checksum=paper_checksum is not None,
    )
    if refusal is not None:
        return AttachResult(refusal)
    # A unique violation aborts the statement. The savepoint keeps the transaction
    # open so the existing row can be read back.
    conn.execute("SAVEPOINT publication_asset_insert")
    try:
        inserted = conn.execute(
            """
            INSERT INTO publication_asset (
                publication_asset_id,
                publication_id,
                file_id,
                kind,
                checksum,
                size_bytes,
                mime_type,
                created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING publication_asset_id, publication_id, file_id, kind, checksum,
                      size_bytes, mime_type, created_at, created_by
            """,
            (
                asset_id_for(publication_id, checksum),
                publication_id,
                file_id,
                kind,
                checksum,
                size_bytes,
                mime_type,
                actor_id,
            ),
        ).fetchone()
    except UniqueViolation:
        conn.execute("ROLLBACK TO SAVEPOINT publication_asset_insert")
        found = conn.execute(
            """
            SELECT publication_asset_id
            FROM publication_asset
            WHERE publication_id = %s
              AND checksum = %s
            """,
            (publication_id, checksum),
        ).fetchone()
        if found is None:
            raise
        return AttachResult("already_attached", publication_asset_id=str(found[0]))
    conn.execute("RELEASE SAVEPOINT publication_asset_insert")
    asset = _asset(inserted)
    return AttachResult("attached", publication_asset_id=asset.publication_asset_id, asset=asset)


def _remove(conn: Any, publication_id: str, publication_asset_id: str) -> RemoveResult:
    deleted = conn.execute(
        """
        DELETE FROM publication_asset
        WHERE publication_asset_id = %s
          AND publication_id = %s
        RETURNING publication_asset_id, publication_id, file_id, kind, checksum,
                  size_bytes, mime_type, created_at, created_by
        """,
        (publication_asset_id, publication_id),
    ).fetchone()
    if deleted is None:
        return RemoveResult("not_found")
    return RemoveResult("removed", asset=_asset(deleted))


def _list_assets(conn: Any, publication_id: str) -> tuple[Asset, ...] | None:
    found = conn.execute(
        """
        SELECT 1
        FROM publication
        WHERE publication_id = %s
        """,
        (publication_id,),
    ).fetchone()
    if found is None:
        return None
    rows = conn.execute(
        """
        SELECT publication_asset_id, publication_id, file_id, kind, checksum,
               size_bytes, mime_type, created_at, created_by
        FROM publication_asset
        WHERE publication_id = %s
        ORDER BY created_at ASC, publication_asset_id ASC
        """,
        (publication_id,),
    ).fetchall()
    return tuple(_asset(row) for row in rows)


def _asset(row: tuple[object, ...]) -> Asset:
    return Asset(
        publication_asset_id=str(row[0]),
        publication_id=str(row[1]),
        file_id=str(row[2]),
        kind=str(row[3]),
        checksum=str(row[4]),
        size_bytes=int(row[5]),  # type: ignore[arg-type]
        mime_type=str(row[6]),
        created_at=row[7],  # type: ignore[arg-type]
        created_by=str(row[8]),
    )


def _note_page_file(conn: Any, file_id: str) -> None:
    conn.execute(
        """
        INSERT INTO files (file_id, purpose, checksum)
        VALUES (%s, 'page', 'checksum-d8a-page')
        """,
        (file_id,),
    )


def _note_paper(conn: Any, file_id: str | None, checksum: str | None, token: str) -> None:
    conn.execute(
        """
        INSERT INTO papers (
            paper_id, teacher_id, student_id, subject_id,
            question_version_id, answer_version_id, asset_ids,
            layout_template_id, review_version_id, file_id,
            status, item_order, file_checksum, formula
        )
        VALUES (
            %s, 'teacher-d8a', 'student-d8a', 'subj-d8a',
            'q-d8a', 'a-d8a', ARRAY[]::text[],
            'layout-d8a', 'rev-d8a', %s,
            'issued', ARRAY[]::text[], %s, 'formula-d8a'
        )
        """,
        ("paper-d8a-" + token, file_id, checksum),
    )


def _clear_privacy_notes(conn: Any) -> None:
    conn.execute("DELETE FROM papers WHERE paper_id LIKE 'paper-d8a-%'")
    conn.execute("DELETE FROM files WHERE checksum = 'checksum-d8a-page'")
