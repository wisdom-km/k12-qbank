"""Session cookie, CSRF, and the actor taken from the session."""

from __future__ import annotations

import hashlib
import os
import re
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from http_client import signed_client

_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
_PERMISSIONS = "camera=(), microphone=(), geolocation=(), interest-cohort=()"


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

    def test_post_without_the_csrf_header_is_forbidden(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            signed = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            self.assertEqual(signed.status_code, 200)
            refused = client.post("/api/logout")
            self.assertEqual(refused.status_code, 403)
            self.assertEqual(refused.json()["code"], "csrf")
            self.assertEqual(refused.headers["content-security-policy"], _CSP)

    def test_a_different_csrf_token_is_forbidden(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            signed = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            token = signed.json()["csrf_token"]
            wrong = ("b" if token.startswith("a") else "a") + token[1:]
            self.assertEqual(len(wrong), len(token))
            self.assertNotEqual(wrong, token)
            refused = client.post("/api/logout", headers={"X-K12-CSRF": wrong})
            self.assertEqual(refused.status_code, 403)
            self.assertEqual(refused.json()["code"], "csrf")

    def test_get_does_not_check_csrf(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            signed = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            self.assertEqual(signed.status_code, 200)
            session = client.get("/api/session")
            self.assertEqual(session.status_code, 200)
            self.assertNotIn("x-k12-csrf", {name.lower() for name in session.request.headers})

    def test_security_headers_are_on_unless_the_switch_is_zero(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            health = client.get("/health")
            self.assertEqual(health.headers["content-security-policy"], _CSP)
            self.assertEqual(health.headers["permissions-policy"], _PERMISSIONS)
            denied = client.get("/api/session")
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(denied.headers["content-security-policy"], _CSP)
            self.assertEqual(denied.headers["permissions-policy"], _PERMISSIONS)
            self.assertEqual(denied.headers["x-frame-options"], "DENY")
        with mock.patch.dict(os.environ, {"K12_SECURITY_HEADERS": "0"}):
            with TestClient(create_app(seed=True)) as client:
                health = client.get("/health")
                self.assertNotIn("content-security-policy", health.headers)
                self.assertNotIn("permissions-policy", health.headers)
                self.assertEqual(health.headers["x-frame-options"], "DENY")

    def test_own_sessions_return_a_prefix_and_write_no_audit(self) -> None:
        with TestClient(create_app(seed=True)) as client:
            signed = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            self.assertEqual(signed.status_code, 200)
            db = client.app.state.loop.identity
            before = len(db.audits.rows)
            listed = client.get("/api/account/sessions")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(len(db.audits.rows), before)
            body = listed.json()
            self.assertEqual(set(body), {"sessions"})
            self.assertEqual(len(body["sessions"]), 1)
            row = body["sessions"][0]
            self.assertEqual(set(row), {"issued_at", "last_seen_at", "ip_hash_prefix"})
            full = hashlib.sha256(b"testclient").hexdigest()
            self.assertEqual(row["ip_hash_prefix"], full[:8])
            self.assertNotIn(full, listed.text)
            self.assertNotIn(signed.json()["csrf_token"], listed.text)
            sid = client.cookies.get("k12_sid")
            current = db.sessions.get(sid)
            db.sessions.put(replace(current, ip_hash="short"))
            short = client.get("/api/account/sessions")
            self.assertEqual(short.json()["sessions"][0]["ip_hash_prefix"], "")
            current = db.sessions.get(sid)
            db.sessions.put(replace(current, ip_hash="abcdefgh"))
            eight = client.get("/api/account/sessions")
            self.assertEqual(eight.json()["sessions"][0]["ip_hash_prefix"], "abcdefgh")

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
            for path in ("/", "/login", "/admin", "/account", "/papers/paper-synth/grade"):
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
        self.assertNotIn("/account", paths)
        self.assertNotIn("/papers/{paper_id}/grade", paths)
        self.assertIn("/api/account/sessions", paths)
