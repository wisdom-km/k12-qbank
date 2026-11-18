"""One up or one down holds pg_advisory_xact_lock for the whole plan."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from backend.bootstrap.compose import repo_root
from backend.bootstrap.migrate import LOCK_KEY, discover, migrate

_PROBE = "c2_lock_probe"
_PARALLEL = "c2_lock_parallel"


class MigrateLockTest(unittest.TestCase):
    def test_lock_key_is_the_adr_constant(self) -> None:
        self.assertEqual(LOCK_KEY, int.from_bytes(b"k12mig01", "big", signed=True))
        self.assertEqual(LOCK_KEY, 7724010281418305585)
        source = Path(__file__).resolve().parents[1] / "backend" / "bootstrap" / "migrate.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))', text)
        self.assertNotIn("autocommit=True", text)

    def test_a_held_lock_blocks_up_until_released(self) -> None:
        dsn = _dsn(self)
        import psycopg

        holder = psycopg.connect(dsn, autocommit=True)
        finished = threading.Event()
        box: dict[str, object] = {}

        def run() -> None:
            try:
                box["applied"] = migrate(dsn, repo_root(), "up")
            except Exception as exc:
                box["error"] = exc
            finally:
                finished.set()

        thread = threading.Thread(target=run, daemon=True)
        try:
            holder.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,)).fetchone()
            thread.start()
            self.assertTrue(_blocked(dsn), "up did not wait on the advisory lock")
            time.sleep(0.4)
            self.assertFalse(finished.is_set())
            holder.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,)).fetchone()
            self.assertTrue(finished.wait(20))
        finally:
            holder.close()
            thread.join(5)
        self.assertNotIn("error", box)
        self.assertIsInstance(box["applied"], list)
        self.assertEqual(_versions(dsn), {item.version for item in discover(repo_root())})

    def test_two_ups_apply_a_new_version_once(self) -> None:
        dsn = _dsn(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _migration(
                root,
                "V902",
                "CREATE TABLE c2_lock_parallel (id int);\n",
                "DROP TABLE IF EXISTS c2_lock_parallel;\n",
            )
            barrier = threading.Barrier(2)
            results: list[list[str]] = []
            errors: list[BaseException] = []
            gate = threading.Lock()

            def run() -> None:
                barrier.wait(5)
                try:
                    applied = migrate(dsn, root, "up")
                except Exception as exc:
                    with gate:
                        errors.append(exc)
                    return
                with gate:
                    results.append(applied)

            threads = [threading.Thread(target=run, daemon=True) for _ in range(2)]
            try:
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(30)
                self.assertEqual(errors, [])
                self.assertEqual(sorted(len(item) for item in results), [0, 1])
                self.assertEqual({version for item in results for version in item}, {"V902"})
                self.assertEqual(_count(dsn, "V902"), 1)
                self.assertIsNotNone(_regclass(dsn, _PARALLEL))
            finally:
                for thread in threads:
                    thread.join(2)
                _cleanup(dsn, "V902", _PARALLEL)

    def test_a_failed_version_rolls_the_plan_back(self) -> None:
        dsn = _dsn(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _migration(
                root,
                "V901",
                "CREATE TABLE c2_lock_probe (id int);\nSELECT 1/0;\n",
                "DROP TABLE IF EXISTS c2_lock_probe;\n",
            )
            try:
                with self.assertRaises(Exception):
                    migrate(dsn, root, "up")
                self.assertIsNone(_regclass(dsn, _PROBE))
                self.assertEqual(_count(dsn, "V901"), 0)
                self.assertIn("V001", _versions(dsn))
            finally:
                _cleanup(dsn, "V901", _PROBE)


def _dsn(case: unittest.TestCase) -> str:
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        case.skipTest("K12_PG_DSN is not set")
    return dsn


def _migration(root: Path, version: str, up_sql: str, down_sql: str) -> None:
    folder = root / "backend" / "c2probe" / "migrations"
    folder.mkdir(parents=True)
    (folder / f"{version}__probe.sql").write_text(up_sql, encoding="utf-8")
    (folder / f"{version}__probe.down.sql").write_text(down_sql, encoding="utf-8")


def _versions(dsn: str) -> set[str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row[0]) for row in rows}


def _count(dsn: str, version: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT count(*) FROM schema_migrations WHERE version = %s",
            (version,),
        ).fetchone()
    return int(row[0]) if row is not None else 0


def _regclass(dsn: str, name: str) -> object:
    import psycopg

    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()
    return None if row is None else row[0]


def _blocked(dsn: str) -> bool:
    import psycopg

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with psycopg.connect(dsn, autocommit=True) as conn:
            row = conn.execute(
                """
                SELECT count(*) FROM pg_stat_activity
                WHERE wait_event_type = 'Lock' AND query LIKE %s
                """,
                ("%pg_advisory_xact_lock%",),
            ).fetchone()
        if row is not None and int(row[0]) >= 1:
            return True
        time.sleep(0.05)
    return False


def _cleanup(dsn: str, version: str, table: str) -> None:
    import psycopg

    drops = {
        "c2_lock_probe": "DROP TABLE IF EXISTS c2_lock_probe",
        "c2_lock_parallel": "DROP TABLE IF EXISTS c2_lock_parallel",
    }
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(drops[table])
        conn.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))
