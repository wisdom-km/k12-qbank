"""V018 on the scratch database. Skipped unless K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest


class BookMigrationTest(unittest.TestCase):
    def test_v018_up_down_up(self) -> None:
        dsn = os.environ.get("K12_PG_DSN", "").strip()
        if not dsn:
            self.skipTest("K12_PG_DSN is not set")
        _v018_round_trip(dsn)


def _v018_round_trip(dsn: str) -> None:
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    item = next(row for row in discover(root) if row.version == "V018")
    _expect_v018(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V018",))
        _expect_v018(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v018(dsn, True)


def _expect_v018(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        book = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'book'"
        ).fetchone()
        lesson = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'book_lesson'"
        ).fetchone()
        column = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'approvals' AND column_name IN ('book_id', 'pdf_page')
            """
        ).fetchall()
    if present:
        if book is None or lesson is None or len(column) != 2:
            raise AssertionError("V018 tables or columns are missing")
        return
    if book is not None or lesson is not None or column:
        raise AssertionError("V018 tables or columns are still present")
