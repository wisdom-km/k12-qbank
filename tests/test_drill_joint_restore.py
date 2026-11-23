"""Joint restore drill. The live database name is always refused.

The round trip runs only when K12_PG_DSN names a scratch database.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from scripts.drill_joint_restore import database_name, refused

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "drill_joint_restore.py"


class JointRestoreGuardTest(unittest.TestCase):
    def test_the_live_database_name_is_refused(self) -> None:
        self.assertTrue(refused("k12"))
        self.assertTrue(refused("postgres"))
        self.assertTrue(refused("k12_m11_src"))
        self.assertTrue(refused("k12_m11_dst"))
        self.assertFalse(refused("k12_d5_schema"))
        self.assertEqual(database_name("postgresql://role@127.0.0.1:5432/k12_d5_schema"), "k12_d5_schema")


class JointRestoreDrillTest(unittest.TestCase):
    def test_scratch_database_and_two_files_restore_together(self) -> None:
        dsn = os.environ.get("K12_PG_DSN", "").strip()
        if not dsn:
            self.skipTest("K12_PG_DSN is not set")
        if refused(database_name(dsn)):
            self.fail(f"refusing database {database_name(dsn)}")
        env = os.environ.copy()
        env["K12_PG_DSN"] = dsn
        completed = subprocess.run(
            [sys.executable, str(_SCRIPT)],
            cwd=_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        secret = urlsplit(dsn).password or ""
        if secret:
            self.assertNotIn(secret, completed.stdout)
            self.assertNotIn(secret, completed.stderr)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("DRILL PASS:", completed.stdout)
        self.assertIn("database=k12_m11_dst", completed.stdout)
        self.assertIn("files=2", completed.stdout)
        self.assertNotIn("database=k12 ", completed.stdout)
