"""V001 is discovered, and the domain does not contain SQL."""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.bootstrap.migrate import discover, sql_statements

ROOT = Path(__file__).resolve().parents[2]


class MigrationFilesTest(unittest.TestCase):
    def test_v001_has_up_and_down(self) -> None:
        found = discover(ROOT)
        self.assertEqual([item.version for item in found], ["V001"])
        self.assertTrue(found[0].down.is_file())
        up = "\n".join(sql_statements(found[0].up.read_text(encoding="utf-8")))
        down = "\n".join(sql_statements(found[0].down.read_text(encoding="utf-8")))
        for name in ("users", "sessions", "students", "teacher_grants", "login_attempts", "audit_events"):
            self.assertIn(name, up)
            self.assertIn(name, down)
        self.assertIn("teacher_grants_one_active", up)
        self.assertIn("jsonb", up.lower())
        self.assertNotIn("schema_migrations", up)

    def test_domain_and_application_do_not_import_the_driver(self) -> None:
        base = ROOT / "backend" / "identity"
        for folder in ("domain", "application"):
            for path in (base / folder).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("psycopg", text)
                self.assertNotIn("INSERT ", text)
                self.assertNotIn("SELECT ", text)
