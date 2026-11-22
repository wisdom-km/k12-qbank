"""Publication list contract. Memory always runs. PostgreSQL runs when K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest

from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.catalog.domain.publication import Publication


class PublicationListCases:
    publications: object

    def test_empty_store_returns_an_empty_page(self) -> None:
        rows, total = self._page()
        self.assertEqual(rows, ())
        self.assertEqual(total, 0)

    def test_one_publication_returns_that_row(self) -> None:
        row = _row("pub-one", "q-list-one", "a-list-one", "subj-list-one", "active")
        self._put(row)
        rows, total = self._page()
        self.assertEqual(rows, (row,))
        self.assertEqual(total, 1)

    def test_status_active_excludes_retired_and_unfiltered_keeps_both(self) -> None:
        active = _row("pub-live", "q-list-live", "a-list-live", "subj-list-math", "active")
        retired = _row("pub-old", "q-list-old", "a-list-old", "subj-list-math", "retired")
        self._put(retired)
        self._put(active)
        everything, total = self._page()
        self.assertEqual(total, 2)
        self.assertEqual([row.publication_id for row in everything], ["pub-live", "pub-old"])
        active_rows, active_total = self._page(status="active")
        self.assertEqual(active_rows, (active,))
        self.assertEqual(active_total, 1)

    def test_subject_filter(self) -> None:
        math_row = _row("pub-math", "q-list-math", "a-list-math", "subj-list-math", "active")
        science_row = _row("pub-sci", "q-list-sci", "a-list-sci", "subj-list-sci", "active")
        self._put(science_row)
        self._put(math_row)
        rows, total = self._page(subject_id="subj-list-math")
        self.assertEqual(rows, (math_row,))
        self.assertEqual(total, 1)

    def test_question_and_answer_filter_together(self) -> None:
        wanted = _row("pub-pair", "q-list-pair", "a-list-pair", "subj-list-math", "active")
        other = _row("pub-other", "q-list-other", "a-list-other", "subj-list-math", "retired")
        self._put(other)
        self._put(wanted)
        rows, total = self._page(question_version_id="q-list-pair", answer_version_id="a-list-pair")
        self.assertEqual(rows, (wanted,))
        self.assertEqual(total, 1)

    def test_page_is_ordered_by_publication_id(self) -> None:
        self._put(_row("pub-c", "q-list-c", "a-list-c", "subj-list-math", "active"))
        self._put(_row("pub-a", "q-list-a", "a-list-a", "subj-list-math", "retired"))
        self._put(_row("pub-b", "q-list-b", "a-list-b", "subj-list-math", "active"))
        rows, total = self._page()
        self.assertEqual(total, 3)
        self.assertEqual([row.publication_id for row in rows], ["pub-a", "pub-b", "pub-c"])

    def test_offset_and_limit_clamp_and_total_ignores_the_page(self) -> None:
        for index in range(201):
            token = f"{index:03d}"
            self._put(_row(f"pub-{token}", f"q-list-{token}", f"a-list-{token}", "subj-list-clamp", "active"))
        first, total = self._page(offset=-1, limit=1)
        self.assertEqual(total, 201)
        self.assertEqual([row.publication_id for row in first], ["pub-000"])
        one, total_one = self._page(limit=0)
        self.assertEqual(total_one, 201)
        self.assertEqual(len(one), 1)
        default_rows, default_total = self._page()
        self.assertEqual(default_total, 201)
        self.assertEqual(len(default_rows), 50)
        self.assertEqual(default_rows[0].publication_id, "pub-000")
        clamped, clamped_total = self._page(limit=201)
        self.assertEqual(clamped_total, 201)
        self.assertEqual(len(clamped), 200)
        self.assertEqual(clamped[-1].publication_id, "pub-199")
        tail, tail_total = self._page(offset=200, limit=50)
        self.assertEqual(tail_total, 201)
        self.assertEqual([row.publication_id for row in tail], ["pub-200"])

    def _put(self, row: Publication) -> None:
        self.publications.put(row)  # type: ignore[attr-defined]

    def _page(self, **kwargs: object) -> tuple[tuple[Publication, ...], int]:
        return self.publications.list_page(**kwargs)  # type: ignore[attr-defined, no-any-return]


class MemoryPublicationListTest(PublicationListCases, unittest.TestCase):
    def setUp(self) -> None:
        self.publications = MemoryPublications()


class PgPublicationListTest(PublicationListCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_publications import PgPublications

        self.pool = _pool()
        _execute(self.pool, "TRUNCATE TABLE publication RESTART IDENTITY CASCADE")
        self.publications = PgPublications(self.pool)


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


def _execute(pool: object, statement: str, params: tuple[object, ...] = ()) -> None:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement, params)


def _row(
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
