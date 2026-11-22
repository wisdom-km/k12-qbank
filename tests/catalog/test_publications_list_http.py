"""HTTP list for publications. The gate owns login. This read does not require CSRF."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.catalog.domain.publication import Publication

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
_PATH = "/api/admin/publications"


class PublicationListHttpTest(unittest.TestCase):
    def test_http_list_rejects_unauthenticated(self) -> None:
        app = _app()
        with TestClient(app) as anon:
            refused = anon.get(_PATH)
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(refused.json()["code"], "unauthenticated")
        self.assertTrue(refused.json()["request_id"])

    def test_http_list_rejects_teacher(self) -> None:
        app = _app()
        with TestClient(app) as teacher:
            _login(teacher, ACTOR_TEACHER_ID, SYNTH_SECRET)
            refused = teacher.get(_PATH)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "permission_denied")

    def test_http_list_returns_the_page_for_admin(self) -> None:
        app = _app()
        _put(app, "pub-http-one", "q-http-one", "a-http-one", "subj-http-math", "active")
        with TestClient(app) as admin:
            _login_admin(admin)
            listed = admin.get(_PATH)
        self.assertEqual(listed.status_code, 200, listed.text)
        body = listed.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["limit"], 50)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["publication_id"], "pub-http-one")
        self.assertEqual(body["items"][0]["status"], "active")
        self.assertIsNone(body["items"][0]["layout_template_id"])

    def test_http_list_filters_active_status(self) -> None:
        app = _app()
        _put(app, "pub-http-live", "q-http-live", "a-http-live", "subj-http-math", "active")
        _put(app, "pub-http-old", "q-http-old", "a-http-old", "subj-http-math", "retired")
        with TestClient(app) as admin:
            _login_admin(admin)
            listed = admin.get(_PATH, params={"status": "active"})
        self.assertEqual(listed.status_code, 200, listed.text)
        body = listed.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual([item["publication_id"] for item in body["items"]], ["pub-http-live"])

    def test_http_list_rejects_unknown_status(self) -> None:
        app = _app()
        with TestClient(app) as admin:
            _login_admin(admin)
            refused = admin.get(_PATH, params={"status": "foo"})
        self.assertEqual(refused.status_code, 422)

    def test_http_list_clamps_limit_201_to_200(self) -> None:
        app = _app()
        with TestClient(app) as admin:
            _login_admin(admin)
            listed = admin.get(_PATH, params={"limit": 201})
        self.assertEqual(listed.status_code, 200, listed.text)
        body = listed.json()
        self.assertEqual(body["limit"], 200)
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["items"], [])


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


def _put(app: object, publication_id: str, question_id: str, answer_id: str, subject_id: str, status: str) -> None:
    app.state.loop.publications.put(  # type: ignore[attr-defined]
        Publication(
            publication_id=publication_id,
            question_version_id=question_id,
            answer_version_id=answer_id,
            subject_id=subject_id,
            status=status,
        )
    )
