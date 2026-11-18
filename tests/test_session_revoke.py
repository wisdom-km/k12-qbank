"""Admin session revoke, and the cookies that die after disable or password reset."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
TEACH_USER = "teacher.one"
TEACH_SECRET = "teach-pass1"
NEXT_SECRET = "new-pass123"


class SessionRevokeHttpTest(unittest.TestCase):
    def test_disable_and_reset_make_the_old_cookie_unauthorized(self) -> None:
        app = _app()
        with TestClient(app) as admin, TestClient(app) as teacher:
            admin_token = _login_admin(admin)
            created = admin.post(
                "/api/admin/teachers",
                json={"username": TEACH_USER, "secret": TEACH_SECRET},
                headers={"X-K12-CSRF": admin_token},
            )
            self.assertEqual(created.status_code, 200, created.text)
            teacher_id = created.json()["user_id"]
            _login(teacher, TEACH_USER, TEACH_SECRET)
            self.assertEqual(teacher.get("/api/session").status_code, 200)
            disabled = admin.post(
                f"/api/admin/teachers/{teacher_id}/disable",
                headers={"X-K12-CSRF": admin_token},
            )
            self.assertEqual(disabled.status_code, 200, disabled.text)
            self.assertEqual(teacher.get("/api/session").status_code, 401)
            enabled = admin.post(
                f"/api/admin/teachers/{teacher_id}/enable",
                headers={"X-K12-CSRF": admin_token},
            )
            self.assertEqual(enabled.status_code, 200, enabled.text)
            _login(teacher, TEACH_USER, TEACH_SECRET)
            self.assertEqual(teacher.get("/api/session").status_code, 200)
            reset = admin.post(
                f"/api/admin/teachers/{teacher_id}/password",
                json={"secret": NEXT_SECRET},
                headers={"X-K12-CSRF": admin_token},
            )
            self.assertEqual(reset.status_code, 200, reset.text)
            self.assertEqual(teacher.get("/api/session").status_code, 401)
            _login(teacher, TEACH_USER, NEXT_SECRET)
            self.assertEqual(teacher.get("/api/session").status_code, 200)

    def test_admin_can_revoke_their_own_session(self) -> None:
        app = _app()
        with TestClient(app) as admin, TestClient(app) as teacher:
            admin_token = _login_admin(admin)
            admin_id = admin.get("/api/session").json()["user_id"]
            teacher_token = _login(teacher, _teacher_name(), _teacher_secret())
            refused = teacher.post(
                f"/api/admin/users/{admin_id}/sessions/revoke",
                headers={"X-K12-CSRF": teacher_token},
            )
            self.assertEqual(refused.status_code, 403)
            self.assertEqual(refused.json()["code"], "permission_denied")
            self.assertEqual(teacher.get("/api/session").status_code, 200)
            missing_header = admin.post(f"/api/admin/users/{admin_id}/sessions/revoke")
            self.assertEqual(missing_header.status_code, 403)
            self.assertEqual(missing_header.json()["code"], "csrf")
            self.assertEqual(admin.get("/api/session").status_code, 200)
            unknown = admin.post(
                "/api/admin/users/missing-user/sessions/revoke",
                headers={"X-K12-CSRF": admin_token},
            )
            self.assertEqual(unknown.status_code, 404)
            self.assertEqual(unknown.json()["code"], "not_found")
            self.assertNotIn("session_id", unknown.text)
            revoked = admin.post(
                f"/api/admin/users/{admin_id}/sessions/revoke",
                headers={"X-K12-CSRF": admin_token},
            )
            self.assertEqual(revoked.status_code, 200, revoked.text)
            self.assertEqual(revoked.json(), {"revoked": 1})
            self.assertNotIn("session_id", revoked.text)
            self.assertEqual(admin.get("/api/session").status_code, 401)
            self.assertEqual(teacher.get("/api/session").status_code, 200)


def _app() -> object:
    with mock.patch.dict(
        os.environ,
        {
            "K12_BOOTSTRAP_ADMIN_USERNAME": ADMIN_USER,
            "K12_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_SECRET,
        },
    ):
        return create_app(seed=True)


def _login_admin(client: TestClient) -> str:
    token = _login(client, ADMIN_USER, ADMIN_SECRET)
    changed = client.post(
        "/api/account/password",
        json={"old_secret": ADMIN_SECRET, "new_secret": ADMIN_NEXT},
        headers={"X-K12-CSRF": token},
    )
    if changed.status_code != 200:
        raise AssertionError(changed.text)
    return token


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
