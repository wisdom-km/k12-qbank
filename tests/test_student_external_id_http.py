"""Student numbers are visible only to an admin or a teacher with a grant."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"


class StudentExternalIdHttpTest(unittest.TestCase):
    def test_admin_response_includes_external_id(self) -> None:
        external_id = "synth-http-0001"
        app = _app()
        with TestClient(app) as admin:
            token = _login_admin(admin)
            created = admin.post("/api/admin/students", json=_body(external_id), headers=_csrf(token))
            self.assertEqual(created.status_code, 200, created.text)
            body = created.json()
            student_id = body["student_id"]
            self.assertEqual(body["external_id"], external_id)
            self.assertIsNone(body["name"])
            self.assertNotEqual(student_id, external_id)
            listed = admin.get("/api/admin/students")
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertIn(external_id, listed.text)
            detail = admin.get("/api/students/" + student_id)
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["external_id"], external_id)
            self.assertEqual(detail.json()["student_id"], student_id)

    def test_authorized_teacher_sees_external_id(self) -> None:
        app = _app()
        with TestClient(app) as teacher:
            token = _login(teacher, ACTOR_TEACHER_ID, SYNTH_SECRET)
            listed = teacher.get("/api/students", headers=_csrf(token))
            self.assertEqual(listed.status_code, 200, listed.text)
            rows = {row["student_id"]: row for row in listed.json()["students"]}
            self.assertEqual(rows["student-synth"]["external_id"], "synth-0001")
            detail = teacher.get("/api/students/student-synth", headers=_csrf(token))
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["external_id"], "synth-0001")
            self.assertEqual(detail.json()["student_id"], "student-synth")

    def test_unauthorized_teacher_cannot_read_the_student(self) -> None:
        external_id = "synth-http-0002"
        app = _app()
        with TestClient(app) as client:
            admin_token = _login_admin(client)
            created = client.post("/api/admin/students", json=_body(external_id), headers=_csrf(admin_token))
            self.assertEqual(created.status_code, 200, created.text)
            student_id = created.json()["student_id"]
            client.post("/api/logout", headers=_csrf(admin_token))
            teacher_token = _login(client, ACTOR_TEACHER_ID, SYNTH_SECRET)
            hidden = client.get("/api/students/" + student_id, headers=_csrf(teacher_token))
            self.assertEqual(hidden.status_code, 404)
            self.assertEqual(hidden.json()["code"], "not_found")
            self.assertNotIn(external_id, hidden.text)
            listed = client.get("/api/students", headers=_csrf(teacher_token))
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertNotIn(external_id, listed.text)
            self.assertNotIn(student_id, listed.text)


def _app() -> object:
    with mock.patch.dict(
        os.environ,
        {
            "K12_BOOTSTRAP_ADMIN_USERNAME": ADMIN_USER,
            "K12_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_SECRET,
            "K12_LOG_FILE": "0",
        },
    ):
        return create_app(seed=True)


def _login_admin(client: TestClient) -> str:
    token = _login(client, ADMIN_USER, ADMIN_SECRET)
    changed = client.post(
        "/api/account/password",
        json={"old_secret": ADMIN_SECRET, "new_secret": ADMIN_NEXT},
        headers=_csrf(token),
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


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


def _body(external_id: str) -> dict[str, str]:
    return {"external_id": external_id, "grade": "g7", "subject_id": "math"}
