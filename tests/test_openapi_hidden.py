"""The synthetic HTTP app does not publish OpenAPI unless a script asks for a schema."""

from __future__ import annotations

import unittest

from backend.bootstrap.http_app import create_app


class OpenApiHiddenTest(unittest.TestCase):
    def test_default_app_does_not_publish_openapi(self) -> None:
        app = create_app(seed=False)
        self.assertIsNone(app.docs_url)
        self.assertIsNone(app.redoc_url)
        self.assertIsNone(app.openapi_url)

    def test_export_builds_a_schema_without_listening(self) -> None:
        app = create_app(seed=False, openapi=True)
        self.assertEqual(app.openapi_url, "/openapi.json")
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "k12-qbank")
        self.assertIn("/health", schema["paths"])
