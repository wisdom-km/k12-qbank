"""production refuses an incomplete volcengine selection without printing the key."""

from __future__ import annotations

import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock

from backend.bootstrap.http_app import create_app


class ProviderStartupTest(unittest.TestCase):
    def test_production_volcengine_names_the_missing_variable(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        env = {
            "K12_ENV": "production",
            "K12_AI_PROVIDER": "volcengine",
            "K12_AI_BASE_URL": "",
            "K12_AI_MODEL": "",
            "K12_AI_API_KEY": "zz9probe",
            "K12_PG_DSN": "",
            "K12_LOG_FILE": "0",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    create_app(seed=False)
        text = stdout.getvalue() + stderr.getvalue()
        self.assertIn("K12_AI_BASE_URL", text)
        self.assertIn("K12_AI_MODEL", text)
        self.assertNotIn("zz9probe", text)

    def test_unknown_provider_exits(self) -> None:
        stderr = StringIO()
        with mock.patch.dict(os.environ, {"K12_AI_PROVIDER": "other", "K12_ENV": "development", "K12_LOG_FILE": "0"}):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    create_app(seed=False)
        self.assertIn("K12_AI_PROVIDER", stderr.getvalue())
