"""The logging scanner rejects the new secret names and allows audit ids."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scanner():
    path = ROOT / "scripts" / "check_logging.py"
    spec = importlib.util.spec_from_file_location("check_logging", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_logging")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LogScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scan = scanner()

    def test_new_secret_names_are_rejected(self) -> None:
        text = (ROOT / "scripts" / "check_logging.py").read_text(encoding="utf-8")
        for word in ("password_hash", "session_id", "csrf_token", "authorization", "cookie"):
            self.assertIn(word, text)
        self.assertTrue(self.scan.line_is_secret("logger.log(password_hash=stored)"))
        self.assertTrue(self.scan.line_is_secret("logger.log(session_id=value)"))
        self.assertTrue(self.scan.line_is_secret("logger.log(csrf_token=value)"))
        self.assertTrue(self.scan.line_is_secret("logger.log(authorization=value)"))
        self.assertTrue(self.scan.line_is_secret("logger.log(cookie=value)"))

    def test_audit_call_may_name_actor_and_target(self) -> None:
        line = 'logger.log(audit=True, actor_user_id=actor, target_kind="user", target_id=row)'
        self.assertFalse(self.scan.line_is_secret(line))
        banned = 'logger.log(audit=True, actor_user_id=actor, csrf_token=value)'
        self.assertTrue(self.scan.line_is_secret(banned))

    def test_scanner_covers_identity_and_bootstrap(self) -> None:
        roots = ("backend/identity", "backend/bootstrap")
        body = (ROOT / "scripts" / "check_logging.py").read_text(encoding="utf-8")
        self.assertIn('CORE = ROOT / "backend"', body)
        for root in roots:
            self.assertTrue((ROOT / root).is_dir() or root.endswith("identity"))
