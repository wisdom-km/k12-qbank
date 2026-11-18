"""The synthetic HTTP app does not publish OpenAPI unless the switch is on."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from scripts.export_openapi import schema_text

ROOT = Path(__file__).resolve().parents[1]
EXPORTED = ROOT / "apps" / "web" / "src" / "api.openapi.json"


class OpenApiHiddenTest(unittest.TestCase):
    def test_default_app_does_not_publish_openapi(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("K12_OPENAPI", None)
            app = create_app(seed=False)
        self.assertIsNone(app.docs_url)
        self.assertIsNone(app.redoc_url)
        self.assertIsNone(app.openapi_url)
        with TestClient(app) as client:
            self.assertEqual(client.get("/docs").status_code, 404)
            self.assertEqual(client.get("/openapi.json").status_code, 404)

    def test_switch_opens_docs_only_when_set_to_one(self) -> None:
        with mock.patch.dict(os.environ, {"K12_OPENAPI": "1"}):
            opened = create_app(seed=False)
            forced_off = create_app(seed=False, openapi=False)
        self.assertEqual(opened.docs_url, "/docs")
        self.assertEqual(opened.openapi_url, "/openapi.json")
        self.assertIsNone(forced_off.openapi_url)
        with mock.patch.dict(os.environ, {"K12_OPENAPI": "0"}):
            closed = create_app(seed=False)
        self.assertIsNone(closed.docs_url)
        with TestClient(opened) as client:
            self.assertEqual(client.get("/docs").status_code, 200)
            body = client.get("/openapi.json")
            self.assertEqual(body.status_code, 200)
            self.assertIn("/health", body.json()["paths"])

    def test_export_builds_a_schema_without_listening(self) -> None:
        app = create_app(seed=False, openapi=True)
        self.assertEqual(app.openapi_url, "/openapi.json")
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "k12-qbank")
        self.assertIn("/health", schema["paths"])
        self.assertIn("/api/account/sessions", schema["paths"])

    def test_committed_openapi_matches_the_export(self) -> None:
        fresh = json.loads(schema_text())
        committed = json.loads(EXPORTED.read_text(encoding="utf-8"))
        self.assertEqual(committed, fresh)
        self.assertIn("/api/account/sessions", committed["paths"])
