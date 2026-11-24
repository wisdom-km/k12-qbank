"""V016 on the scratch database. Skipped unless K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest


class FormulaMigrationTest(unittest.TestCase):
    def test_v016_up_down_up(self) -> None:
        dsn = os.environ.get("K12_PG_DSN", "").strip()
        if not dsn:
            self.skipTest("K12_PG_DSN is not set")
        _v016_round_trip(dsn)


def _v016_round_trip(dsn: str) -> None:
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    item = next(row for row in discover(root) if row.version == "V016")
    _expect_v016(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V016",))
        _expect_v016(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v016(dsn, True)


def _expect_v016(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        names = conn.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE (table_name = 'approvals' AND column_name IN ('stem_parts', 'option_parts'))
               OR (table_name = 'practice_item' AND column_name IN ('stem_parts', 'option_parts', 'formula_draw'))
            """
        ).fetchall()
    found = {(str(row[0]), str(row[1])) for row in names}
    expected = {
        ("approvals", "stem_parts"),
        ("approvals", "option_parts"),
        ("practice_item", "stem_parts"),
        ("practice_item", "option_parts"),
        ("practice_item", "formula_draw"),
    }
    if present and found != expected:
        raise AssertionError("V016 columns missing")
    if not present and found:
        raise AssertionError("V016 columns still present")


if __name__ == "__main__":
    unittest.main()
