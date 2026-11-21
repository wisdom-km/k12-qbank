"""Publication ledger contract. Memory always runs. PostgreSQL runs when K12_PG_DSN is set.

a2, e, and f are PostgreSQL only. Memory does not execute V007, and it has no CHECK or UNIQUE.
a2 uses skipUnless so a run without K12_PG_DSN does not treat the SQL filter as a memory test.
"""

from __future__ import annotations

import os
import unittest

from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.catalog.domain.publication import Publication
from backend.catalog.domain.snapshot import ApprovalSnapshot

_STEM = "计算：(-3)+5"
_RETIRED_REASON = (
    "K12_PG_DSN is empty. Memory does not run V007, so the retired filter is a PostgreSQL test."
)


class PublicationCases:
    publications: object

    def test_grandfather_creates_active_publication_for_each_approved_pair(self) -> None:
        self.apply_grandfather()
        math_row = self.publications.active_of("q-d5-1", "a-d5-1")  # type: ignore[attr-defined]
        science_row = self.publications.active_of("q-d5-4", "a-d5-4")  # type: ignore[attr-defined]
        self.assertIsNotNone(math_row)  # type: ignore[attr-defined]
        self.assertEqual(math_row.subject_id, "math")  # type: ignore[attr-defined]
        self.assertEqual(math_row.status, "active")  # type: ignore[attr-defined]
        self.assertIsNone(math_row.layout_template_id)  # type: ignore[attr-defined]
        self.assertIsNotNone(science_row)  # type: ignore[attr-defined]
        self.assertEqual(science_row.subject_id, "science")  # type: ignore[attr-defined]
        self.assertIsNone(self.publications.active_of("q-d5-2", "a-d5-2"))  # type: ignore[attr-defined]
        self.assertIsNone(self.publications.active_of("q-d5-3", "a-d5-3"))  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            [row.question_version_id for row in self.publications.list_active()],  # type: ignore[attr-defined]
            ["q-d5-1", "q-d5-4"],
        )

    def test_active_of_returns_single_row_when_bound(self) -> None:
        row = _publication("pub-b", "q-b", "a-b", "math", "active")
        self.publications.put(row)  # type: ignore[attr-defined]
        self.assertEqual(self.publications.active_of("q-b", "a-b"), row)  # type: ignore[attr-defined]

    def test_active_of_returns_none_when_no_publication(self) -> None:
        self.assertIsNone(self.publications.active_of("q-missing", "a-missing"))  # type: ignore[attr-defined]

    def test_active_of_returns_none_for_retired_binding(self) -> None:
        self.publications.put(_publication("pub-d", "q-d", "a-d", "math", "retired"))  # type: ignore[attr-defined]
        self.assertIsNone(self.publications.active_of("q-d", "a-d"))  # type: ignore[attr-defined]
        self.assertEqual(self.publications.list_active(), ())  # type: ignore[attr-defined]

    def apply_grandfather(self) -> None:
        raise NotImplementedError


class MemoryPublicationTest(PublicationCases, unittest.TestCase):
    def setUp(self) -> None:
        self.publications = MemoryPublications()

    def apply_grandfather(self) -> None:
        self.publications.fill_grandfather(_samples())


class PgPublicationTest(PublicationCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_publications import PgPublications

        self.pool = _pool()
        _execute(self.pool, "TRUNCATE TABLE publication RESTART IDENTITY CASCADE")
        self.publications = PgPublications(self.pool)

    def apply_grandfather(self) -> None:
        _reapply_v007(self.pool)
        from backend.catalog.adapters.pg_publications import PgPublications

        self.publications = PgPublications(self.pool)

    @unittest.skipUnless(os.environ.get("K12_PG_DSN", "").strip(), _RETIRED_REASON)
    def test_grandfather_skips_retired_approvals(self) -> None:
        self.apply_grandfather()
        self.assertIsNone(self.publications.active_of("q-d5-2", "a-d5-2"))
        count = _scalar(
            self.pool,
            "SELECT count(*) FROM publication WHERE question_version_id = %s",
            ("q-d5-2",),
        )
        self.assertEqual(count, 0)

    def test_unique_constraint_blocks_duplicate_active_binding(self) -> None:
        from psycopg.errors import UniqueViolation

        self.publications.put(_publication("pub-e-1", "q-e", "a-e", "math", "active"))
        with self.assertRaises(UniqueViolation):
            self.publications.put(_publication("pub-e-2", "q-e", "a-e", "math", "active"))

    def test_publication_insert_rejects_unknown_status(self) -> None:
        from psycopg.errors import CheckViolation

        with self.assertRaises(CheckViolation):
            self.publications.put(_publication("pub-f", "q-f", "a-f", "math", "draft"))


def _samples() -> tuple[ApprovalSnapshot, ...]:
    return (
        _snapshot("q-d5-1", "a-d5-1", subject_id="math", question_approved=True, answer_approved=True, retired=False),
        _snapshot("q-d5-2", "a-d5-2", subject_id="math", question_approved=True, answer_approved=True, retired=True),
        _snapshot("q-d5-3", "a-d5-3", subject_id="math", question_approved=True, answer_approved=False, retired=False),
        _snapshot("q-d5-4", "a-d5-4", subject_id="science", question_approved=True, answer_approved=True, retired=False),
    )


def _snapshot(
    question_version_id: str,
    answer_version_id: str,
    *,
    subject_id: str,
    question_approved: bool,
    answer_approved: bool,
    retired: bool,
) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=question_version_id,
        answer_version_id=answer_version_id,
        asset_ids=(),
        layout_template_id="layout-none",
        question_approved=question_approved,
        answer_approved=answer_approved,
        retired=retired,
        subject_id=subject_id,
        item_order=("sq-1",),
        stem=_STEM,
        answer_text="2",
    )


def _publication(
    publication_id: str,
    question_version_id: str,
    answer_version_id: str,
    subject_id: str,
    status: str,
) -> Publication:
    return Publication(
        publication_id=publication_id,
        question_version_id=question_version_id,
        answer_version_id=answer_version_id,
        subject_id=subject_id,
        status=status,
    )


_POOL: object | None = None


def _pool() -> object:
    global _POOL
    if _POOL is not None:
        return _POOL
    from psycopg_pool import ConnectionPool

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import migrate

    dsn = os.environ["K12_PG_DSN"]
    migrate(dsn, repo_root(), "up")
    _POOL = ConnectionPool(dsn, min_size=1, max_size=2, open=True)
    return _POOL


def _reapply_v007(pool: object) -> None:
    from backend.catalog.adapters.pg_approvals import PgApprovals
    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import migrate

    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute("TRUNCATE TABLE approvals RESTART IDENTITY CASCADE")
            conn.execute("DELETE FROM schema_migrations WHERE version = 'V007'")
            conn.execute("DROP TABLE IF EXISTS publication")
    approvals = PgApprovals(pool)
    for snap in _samples():
        approvals.put(snap)
    migrate(os.environ["K12_PG_DSN"], repo_root(), "up")


def _execute(pool: object, statement: str) -> None:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement)


def _scalar(pool: object, statement: str, params: tuple[object, ...]) -> int:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        row = conn.execute(statement, params).fetchone()
    return int(row[0])
