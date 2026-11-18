"""V001 is discovered, and the domain does not contain SQL."""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.bootstrap.migrate import discover, sql_statements

ROOT = Path(__file__).resolve().parents[2]


class MigrationFilesTest(unittest.TestCase):
    def test_v001_has_up_and_down(self) -> None:
        found = discover(ROOT)
        self.assertEqual([item.version for item in found], ["V001", "V002", "V003"])
        self.assertTrue(found[0].down.is_file())
        up = "\n".join(sql_statements(found[0].up.read_text(encoding="utf-8")))
        down = "\n".join(sql_statements(found[0].down.read_text(encoding="utf-8")))
        for name in ("users", "sessions", "students", "teacher_grants", "login_attempts", "audit_events"):
            self.assertIn(name, up)
            self.assertIn(name, down)
        self.assertIn("teacher_grants_one_active", up)
        self.assertIn("jsonb", up.lower())
        self.assertNotIn("schema_migrations", up)
        self.assertTrue(found[1].down.is_file())
        up2 = "\n".join(sql_statements(found[1].up.read_text(encoding="utf-8")))
        down2 = "\n".join(sql_statements(found[1].down.read_text(encoding="utf-8")))
        for name in ("approvals", "papers", "paper_pages", "attempts", "confirmations", "files"):
            self.assertIn(name, up2)
            self.assertIn(name, down2)
        self.assertIn("confirmations_slot_key", up2)
        self.assertNotIn("CREATE TABLE question_option", up2)
        self.assertNotIn("CREATE TABLE answer_version", up2)
        self.assertNotIn("knowledge_point", up2)
        self.assertNotIn("schema_migrations", up2)
        self.assertTrue(found[2].down.is_file())
        up3 = found[2].up.read_text(encoding="utf-8")
        down3 = found[2].down.read_text(encoding="utf-8")
        self.assertIn("must_change_password", up3)
        self.assertIn("DROP COLUMN must_change_password", down3)

    def test_domain_and_application_do_not_import_the_driver(self) -> None:
        base = ROOT / "backend" / "identity"
        for folder in ("domain", "application"):
            for path in (base / folder).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("psycopg", text)
                self.assertNotIn("INSERT ", text)
                self.assertNotIn("SELECT ", text)
