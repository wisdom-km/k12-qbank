"""The bootstrap admin can sign in, then only session, logout, and password until it changes."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
TEACH_SECRET = "teach-pass1"


class MustChangeHttpTest(unittest.TestCase):
    def test_other_calls_wait_until_the_password_changes(self) -> None:
        app = _app()
        with TestClient(app) as anon, TestClient(app) as teacher, TestClient(app) as admin:
            self.assertEqual(anon.get("/health").status_code, 200)
            closed = anon.get("/api/admin/audit")
            self.assertEqual(closed.status_code, 401)
            self.assertEqual(closed.json()["code"], "unauthenticated")
            _login(teacher, _teacher_name(), _teacher_secret())
            denied = teacher.get("/api/admin/audit")
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["code"], "permission_denied")
            self.assertEqual(teacher.get("/api/session").status_code, 200)

            token = _login(admin, ADMIN_USER, ADMIN_SECRET)
            self.assertIn("k12_sid", admin.cookies)
            self.assertEqual(admin.get("/api/session").status_code, 200)
            blocked = admin.get("/api/admin/audit")
            self.assertEqual(blocked.status_code, 403)
            self.assertEqual(blocked.json()["code"], "password_change_required")
            blocked_write = admin.post(
                "/api/admin/teachers",
                json={"username": "teacher.one", "secret": TEACH_SECRET},
            )
            self.assertEqual(blocked_write.status_code, 403)
            self.assertEqual(blocked_write.json()["code"], "password_change_required")
            missing = admin.post(
                "/api/account/password",
                json={"old_secret": ADMIN_SECRET, "new_secret": ADMIN_NEXT},
            )
            self.assertEqual(missing.status_code, 403)
            self.assertEqual(missing.json()["code"], "csrf")
            missing_out = admin.post("/api/logout")
            self.assertEqual(missing_out.status_code, 403)
            self.assertEqual(missing_out.json()["code"], "csrf")
            signed_out = admin.post("/api/logout", headers={"X-K12-CSRF": token})
            self.assertEqual(signed_out.status_code, 200, signed_out.text)
            self.assertEqual(admin.get("/api/session").status_code, 401)

            token = _login(admin, ADMIN_USER, ADMIN_SECRET)
            weak = admin.post(
                "/api/account/password",
                json={"old_secret": ADMIN_SECRET, "new_secret": "short"},
                headers={"X-K12-CSRF": token},
            )
            self.assertEqual(weak.status_code, 400)
            self.assertEqual(weak.json()["code"], "weak_password")
            still = admin.get("/api/admin/audit")
            self.assertEqual(still.status_code, 403)
            self.assertEqual(still.json()["code"], "password_change_required")
            changed = admin.post(
                "/api/account/password",
                json={"old_secret": ADMIN_SECRET, "new_secret": ADMIN_NEXT},
                headers={"X-K12-CSRF": token},
            )
            self.assertEqual(changed.status_code, 200, changed.text)
            self.assertEqual(admin.get("/api/session").json()["csrf_token"], token)
            opened = admin.get("/api/admin/audit")
            self.assertEqual(opened.status_code, 200, opened.text)
            self.assertNotIn(ADMIN_SECRET, opened.text)
            self.assertNotIn(ADMIN_NEXT, opened.text)


def _app() -> object:
    with mock.patch.dict(
        os.environ,
        {
            "K12_BOOTSTRAP_ADMIN_USERNAME": ADMIN_USER,
            "K12_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_SECRET,
        },
    ):
        return create_app(seed=True)


def _login(client: TestClient, username: str, secret: str) -> str:
    response = client.post("/api/login", json={"username": username, "secret": secret})
    if response.status_code != 200:
        raise AssertionError(response.text)
    token = response.json()["csrf_token"]
    if not isinstance(token, str):
        raise AssertionError("csrf token missing")
    return token


def _teacher_name() -> str:
    from backend.bootstrap.synthetic import ACTOR_TEACHER_ID

    return ACTOR_TEACHER_ID


def _teacher_secret() -> str:
    from backend.bootstrap.synthetic import SYNTH_SECRET

    return SYNTH_SECRET
