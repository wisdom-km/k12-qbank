"""HTTP retire for one publication binding. The gate owns login and CSRF."""

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
_PATH = "/api/admin/publications/retire"


class PublicationRetireHttpTest(unittest.TestCase):
    def test_http_retire_rejects_unauthenticated(self) -> None:
        app = _app()
        with TestClient(app) as anon:
            refused = anon.post(_PATH, json=_body("q-http-anon", "a-http-anon"))
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(refused.json()["code"], "unauthenticated")
        self.assertTrue(refused.json()["request_id"])

    def test_http_retire_rejects_non_admin(self) -> None:
        app = _app()
        _bind(app, "q-http-teacher", "a-http-teacher")
        with TestClient(app) as teacher:
            token = _login(teacher, ACTOR_TEACHER_ID, SYNTH_SECRET)
            refused = teacher.post(
                _PATH,
                json=_body("q-http-teacher", "a-http-teacher"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "permission_denied")
        self.assertEqual(_status(app, "q-http-teacher", "a-http-teacher"), "active")

    def test_http_retire_passes_for_admin_when_active(self) -> None:
        app = _app()
        _bind(app, "q-http-live", "a-http-live")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            retired = admin.post(
                _PATH,
                json=_body("q-http-live", "a-http-live"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json(), {"outcome": "retired"})
        self.assertEqual(_status(app, "q-http-live", "a-http-live"), "retired")

    def test_http_retire_is_idempotent_when_already_retired(self) -> None:
        app = _app()
        _bind(app, "q-http-again", "a-http-again")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            first = admin.post(
                _PATH,
                json=_body("q-http-again", "a-http-again"),
                headers={"X-K12-CSRF": token},
            )
            second = admin.post(
                _PATH,
                json=_body("q-http-again", "a-http-again"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), {"outcome": "retired"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json(), {"outcome": "already_retired"})
        self.assertEqual(len(app.state.loop.publications.rows_for("q-http-again", "a-http-again")), 1)
        self.assertEqual(_status(app, "q-http-again", "a-http-again"), "retired")

    def test_http_retire_returns_404_when_binding_absent(self) -> None:
        app = _app()
        with TestClient(app) as admin:
            token = _login_admin(admin)
            missing = admin.post(
                _PATH,
                json=_body("q-http-missing", "a-http-missing"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(missing.status_code, 404)
        body = missing.json()
        self.assertEqual(body["code"], "not_found")
        self.assertTrue(body["message"])
        self.assertTrue(body["request_id"])
        self.assertEqual(app.state.loop.publications.rows_for("q-http-missing", "a-http-missing"), ())

    def test_http_retire_missing_csrf_is_rejected(self) -> None:
        app = _app()
        _bind(app, "q-http-csrf", "a-http-csrf")
        with TestClient(app) as admin:
            _login_admin(admin)
            refused = admin.post(_PATH, json=_body("q-http-csrf", "a-http-csrf"))
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "csrf")
        self.assertEqual(_status(app, "q-http-csrf", "a-http-csrf"), "active")


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


def _bind(app: object, question_id: str, answer_id: str) -> None:
    app.state.loop.publications.put(  # type: ignore[attr-defined]
        Publication(
            publication_id="pub-" + question_id + "-" + answer_id,
            question_version_id=question_id,
            answer_version_id=answer_id,
            subject_id="math",
            status="active",
        )
    )


def _status(app: object, question_id: str, answer_id: str) -> str:
    rows = app.state.loop.publications.rows_for(question_id, answer_id)  # type: ignore[attr-defined]
    return str(rows[0].status)


def _body(question_id: str, answer_id: str) -> dict[str, str]:
    return {"question_version_id": question_id, "answer_version_id": answer_id}
