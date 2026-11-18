"""Session cookie, CSRF, and the actor taken from the session."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from http_client import signed_client


class HttpSessionTest(unittest.TestCase):
    def test_health_is_open_and_session_without_a_cookie_is_generic(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json(), {"status": "ok"})
            session = client.get("/api/session")
            self.assertEqual(session.status_code, 401)
            self.assertEqual(session.json()["code"], "unauthenticated")
            self.assertNotIn("teacher", session.text)

    def test_login_sets_a_cookie_and_the_body_teacher_is_ignored(self) -> None:
        with signed_client() as client:
            session = client.get("/api/session")
            body = session.json()
            self.assertEqual(body["actor_teacher_id"], ACTOR_TEACHER_ID)
            self.assertEqual(body["user_id"], ACTOR_TEACHER_ID)
            self.assertEqual(body["role"], "teacher")
            self.assertEqual(body["display_name"], ACTOR_TEACHER_ID)
            self.assertIn("student-synth", body["student_ids"])
            self.assertNotIn("password", session.text)
            client.post("/api/catalog/q-v1/publish")
            issued = client.post(
                "/api/practice/papers",
                json={
                    "teacher_id": "teacher-b",
                    "student_id": "student-synth",
                    "subject_id": "math",
                    "question_version_id": "q-v1",
                    "review_version_id": "rev-1",
                },
            )
            self.assertEqual(issued.status_code, 200, issued.text)
            self.assertEqual(issued.json()["teacher_id"], ACTOR_TEACHER_ID)

    def test_missing_csrf_is_forbidden_and_a_bad_login_stays_generic(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            bad = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": "not-the-one"})
            self.assertEqual(bad.status_code, 401)
            self.assertEqual(bad.json()["code"], "unauthenticated")
            signed = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            self.assertEqual(signed.status_code, 200)
            refused = client.post("/api/catalog/q-v1/publish")
            self.assertEqual(refused.status_code, 403)
            self.assertEqual(refused.json()["code"], "csrf")
            huge = client.post("/api/login", content=b"{}", headers={"Content-Length": "2000000"})
            self.assertEqual(huge.status_code, 413)

    def test_a_teacher_cannot_create_teachers(self) -> None:
        with signed_client() as client:
            created = client.post("/api/admin/teachers", json={"username": "new-teacher", "secret": "teach-pass1"})
            self.assertEqual(created.status_code, 403)
            self.assertEqual(created.json()["code"], "permission_denied")

    def test_logout_drops_the_session(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            signed = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            token = signed.json()["csrf_token"]
            gone = client.post("/api/logout", headers={"X-K12-CSRF": token})
            self.assertEqual(gone.status_code, 200)
            session = client.get("/api/session")
            self.assertEqual(session.status_code, 401)

    def test_unreachable_database_exits_without_a_loop(self) -> None:
        dsn = "postgresql://k12:changeme@127.0.0.1:1/k12"
        with mock.patch.dict(os.environ, {"K12_PG_DSN": dsn}):
            with self.assertRaises(SystemExit) as caught:
                create_app(persist=True, seed=False)
        self.assertEqual(caught.exception.code, 1)

    def test_spa_paths_serve_index_and_stay_out_of_openapi(self) -> None:
        index = Path(__file__).resolve().parents[1] / "apps" / "web" / "dist" / "index.html"
        if not index.is_file():
            self.skipTest("apps/web/dist is produced by npm run build")
        app = create_app(seed=False, openapi=True)
        with TestClient(app) as client:
            for path in ("/", "/login", "/admin"):
                page = client.get(path)
                self.assertEqual(page.status_code, 200, path)
                self.assertIn('id="root"', page.text)
            script = re.search(r'src="([^"]+)"', client.get("/login").text)
            self.assertIsNotNone(script)
            asset = client.get(script.group(1))
            self.assertEqual(asset.status_code, 200)
            self.assertEqual(client.get("/api/session").status_code, 401)
        paths = app.openapi()["paths"]
        self.assertNotIn("/", paths)
        self.assertNotIn("/login", paths)
        self.assertNotIn("/admin", paths)
