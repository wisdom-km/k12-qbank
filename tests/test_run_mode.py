"""K12_ENV chooses memory or PostgreSQL. A log line never carries the DSN."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from backend.bootstrap.run_mode import choose_persist, require_file_dir
from backend.kernel.log_event import LogEvent

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


class _Capture:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class RunModeTest(unittest.TestCase):
    def test_development_without_a_dsn_warns_and_stays_in_memory(self) -> None:
        logger = _Capture()
        self.assertFalse(choose_persist("", "", logger))
        self.assertFalse(choose_persist(" development ", "  ", logger))
        self.assertEqual([event.outcome for event in logger.events], ["memory", "memory"])
        self.assertEqual(logger.events[0].level, "WARN")
        self.assertEqual(logger.events[0].event, "startup_degraded")

    def test_a_dsn_connects_without_a_startup_line(self) -> None:
        logger = _Capture()
        dsn = "postgresql://k12:changeme@127.0.0.1:5432/k12"
        self.assertTrue(choose_persist("development", dsn, logger))
        self.assertTrue(choose_persist(" production ", dsn, logger))
        self.assertEqual(logger.events, [])

    def test_production_without_a_dsn_exits(self) -> None:
        logger = _Capture()
        with self.assertRaises(SystemExit) as caught:
            choose_persist("production", "", logger)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(len(logger.events), 1)
        self.assertEqual(logger.events[0].level, "ERROR")
        self.assertEqual(logger.events[0].event, "startup_refused")
        self.assertEqual(logger.events[0].outcome, "dsn_required")

    def test_any_other_mode_exits_without_echoing_the_value(self) -> None:
        logger = _Capture()
        with self.assertRaises(SystemExit) as caught:
            choose_persist("Development", "", logger)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(logger.events[0].outcome, "bad_env")
        self.assertNotIn("Development", json.dumps(logger.events[0].fields()))

    def test_file_directory_is_required_only_in_production(self) -> None:
        logger = _Capture()
        require_file_dir("development", "", logger)
        require_file_dir("production", "D:/var/pages", logger)
        self.assertEqual(logger.events, [])
        with self.assertRaises(SystemExit) as caught:
            require_file_dir("production", "  ", logger)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(logger.events[0].outcome, "file_dir_required")

    def test_production_empty_directory_exits_before_a_connection(self) -> None:
        from backend.bootstrap.pg_runtime import open_postgres

        env = {
            "K12_ENV": "production",
            "K12_FILE_DIR": "",
            "K12_PG_DSN": "postgresql://k12:changeme@127.0.0.1:1/k12",
        }
        buffer = StringIO()
        with mock.patch.dict(os.environ, env):
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    open_postgres()
        self.assertEqual(caught.exception.code, 1)
        text = buffer.getvalue()
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["level"], "ERROR")
        self.assertEqual(row["event"], "startup_refused")
        self.assertEqual(row["outcome"], "file_dir_required")
        self.assertNotIn("127.0.0.1", text)
        self.assertNotIn("changeme", text)
        self.assertNotIn("postgresql://", text)

    def test_development_still_reports_an_unreachable_database(self) -> None:
        from backend.bootstrap.pg_runtime import open_postgres

        env = {
            "K12_ENV": "development",
            "K12_FILE_DIR": "",
            "K12_PG_DSN": "postgresql://k12:changeme@127.0.0.1:1/k12",
        }
        buffer = StringIO()
        with mock.patch.dict(os.environ, env):
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    open_postgres()
        self.assertEqual(caught.exception.code, 1)
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["outcome"], "store_failed")
        self.assertNotIn("changeme", lines[0])
        self.assertNotIn("127.0.0.1", lines[0])

    def test_importing_the_app_follows_the_mode(self) -> None:
        refused = _import_app({"K12_ENV": "production", "K12_PG_DSN": "", "K12_FILE_DIR": ""})
        self.assertEqual(refused.returncode, 1)
        refused_line = _only_line(refused.stdout)
        self.assertEqual(refused_line["outcome"], "dsn_required")
        self.assertEqual(refused_line["level"], "ERROR")
        self.assertNotIn("postgresql://", refused.stdout)
        bad = _import_app({"K12_ENV": "nope", "K12_PG_DSN": "", "K12_FILE_DIR": ""})
        self.assertEqual(bad.returncode, 1)
        bad_line = _only_line(bad.stdout)
        self.assertEqual(bad_line["outcome"], "bad_env")
        self.assertNotIn("nope", bad.stdout)
        warned = _import_app({"K12_ENV": "development", "K12_PG_DSN": "", "K12_FILE_DIR": ""})
        self.assertEqual(warned.returncode, 0)
        warned_line = _only_line(warned.stdout)
        self.assertEqual(warned_line["level"], "WARN")
        self.assertEqual(warned_line["outcome"], "memory")


def _import_app(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(overrides)
    code = "import backend.bootstrap.http_app\n"
    return subprocess.run(
        [PY, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _only_line(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssertionError(stdout)
    return json.loads(lines[0])
