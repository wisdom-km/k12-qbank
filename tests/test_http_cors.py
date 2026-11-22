"""Production CORS comes from K12_CORS_ORIGINS. An empty list is not *."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.run_mode import cors_origins
from backend.kernel.log_event import LogEvent

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


class _Capture:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class CorsTest(unittest.TestCase):
    def test_cors_production_requires_origins_env(self) -> None:
        logger = _Capture()
        with self.assertRaises(SystemExit) as missing:
            cors_origins("production", None, logger)
        self.assertEqual(missing.exception.code, 1)
        with self.assertRaises(SystemExit) as blank:
            cors_origins("production", "  , ", logger)
        self.assertEqual(blank.exception.code, 1)
        self.assertEqual([event.outcome for event in logger.events], ["cors_origins_required", "cors_origins_required"])
        self.assertTrue(all(event.level == "ERROR" for event in logger.events))

        refused = _import_app(
            {
                "K12_ENV": "production",
                "K12_PG_DSN": "postgresql://k12:changeme@127.0.0.1:1/k12",
                "K12_FILE_DIR": "D:/var/pages",
                "K12_CORS_ORIGINS": "",
            }
        )
        self.assertEqual(refused.returncode, 1)
        line = _only_line(refused.stdout)
        self.assertEqual(line["level"], "ERROR")
        self.assertEqual(line["event"], "startup_refused")
        self.assertEqual(line["outcome"], "cors_origins_required")
        self.assertNotIn("*", refused.stdout)
        self.assertNotIn("changeme", refused.stdout)
        self.assertNotIn("postgresql://", refused.stdout)

    def test_cors_production_rejects_unlisted_origin(self) -> None:
        env = {"K12_ENV": "production", "K12_CORS_ORIGINS": "https://teacher.example"}
        with mock.patch.dict(os.environ, env):
            with TestClient(create_app(seed=False)) as client:
                denied = client.get("/health", headers={"Origin": "https://other.example"})
                allowed = client.get("/health", headers={"Origin": "https://teacher.example"})
        self.assertNotIn("access-control-allow-origin", _lower_keys(denied.headers))
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "https://teacher.example")
        self.assertEqual(allowed.headers.get("access-control-allow-credentials"), "true")

    def test_cors_development_allows_localhost(self) -> None:
        env = {"K12_ENV": "development", "K12_CORS_ORIGINS": ""}
        with mock.patch.dict(os.environ, env):
            with TestClient(create_app(seed=False)) as client:
                local = client.get("/health", headers={"Origin": "http://localhost:5173"})
                loopback = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
                other = client.get("/health", headers={"Origin": "https://other.example"})
        self.assertEqual(local.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertEqual(loopback.headers.get("access-control-allow-origin"), "http://127.0.0.1:5173")
        self.assertNotIn("access-control-allow-origin", _lower_keys(other.headers))


def _import_app(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(overrides)
    return subprocess.run(
        [PY, "-c", "import backend.bootstrap.http_app"],
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


def _lower_keys(headers: object) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}  # type: ignore[attr-defined]
