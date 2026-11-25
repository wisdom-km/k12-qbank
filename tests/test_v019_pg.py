"""V019 on the scratch database. Skipped unless K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest


class PaperSourceMigrationTest(unittest.TestCase):
    def test_v019_up_down_up(self) -> None:
        dsn = os.environ.get("K12_PG_DSN", "").strip()
        if not dsn:
            self.skipTest("K12_PG_DSN is not set")
        _v019_round_trip(dsn)


def _v019_round_trip(dsn: str) -> None:
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    item = next(row for row in discover(root) if row.version == "V019")
    _expect_v019(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V019",))
        _expect_v019(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v019(dsn, True)


def _expect_v019(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        column = conn.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_name = 'papers' AND column_name = 'source_paper_id'
            """
        ).fetchone()
    if present:
        if column is None or column[0] != "YES":
            raise AssertionError("papers.source_paper_id is missing or not nullable")
        return
    if column is not None:
        raise AssertionError("papers.source_paper_id is still present")
