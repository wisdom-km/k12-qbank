"""HTTP publish for one publication binding. The gate owns login and CSRF."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.catalog.domain.snapshot import ApprovalSnapshot

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
_PATH = "/api/admin/publications/publish"
_RETIRE = "/api/admin/publications/retire"
_STEM = "计算：(-3)+5"


class PublicationPublishHttpTest(unittest.TestCase):
    def test_http_publish_rejects_unauthenticated(self) -> None:
        app = _app()
        with TestClient(app) as anon:
            refused = anon.post(_PATH, json=_body("q-http-pub-anon", "a-http-pub-anon"))
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(refused.json()["code"], "unauthenticated")
        self.assertTrue(refused.json()["request_id"])

    def test_http_publish_rejects_non_admin(self) -> None:
        app = _app()
        _approve(app, "q-http-pub-teacher", "a-http-pub-teacher")
        with TestClient(app) as teacher:
            token = _login(teacher, ACTOR_TEACHER_ID, SYNTH_SECRET)
            refused = teacher.post(
                _PATH,
                json=_body("q-http-pub-teacher", "a-http-pub-teacher"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "permission_denied")
        self.assertEqual(app.state.loop.publications.rows_for("q-http-pub-teacher", "a-http-pub-teacher"), ())

    def test_http_publish_passes_for_admin_when_approved(self) -> None:
        app = _app()
        question_id, answer_id = "q-http-pub-live", "a-http-pub-live"
        _approve(app, question_id, answer_id, subject_id="geom-http")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            published = admin.post(
                _PATH,
                json=_body(question_id, answer_id, layout_template_id="  sheet-1  "),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(published.status_code, 200, published.text)
        publication_id = f"pub-{question_id}-{answer_id}-1"
        self.assertEqual(published.json(), {"outcome": "published", "publication_id": publication_id})
        rows = app.state.loop.publications.rows_for(question_id, answer_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "active")
        self.assertEqual(rows[0].subject_id, "geom-http")
        self.assertEqual(rows[0].layout_template_id, "sheet-1")
        actor = app.state.loop.identity.users.by_username(ADMIN_USER).user_id
        audit = [row for row in app.state.loop.identity.audits.rows if row.action == "publication_published"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].actor_user_id, actor)
        self.assertEqual(audit[0].target_id, publication_id)
        self.assertEqual(audit[0].outcome, "ok")
        self.assertEqual(
            json.loads(audit[0].detail_json),
            {
                "question_version_id": question_id,
                "answer_version_id": answer_id,
                "subject_id": "geom-http",
                "layout_template_id": "sheet-1",
                "sequence": 1,
                "after": {"status": "active"},
            },
        )

    def test_http_publish_returns_409_when_not_approved(self) -> None:
        app = _app()
        _approve(app, "q-http-pub-one", "a-http-pub-one", answer_approved=False)
        with TestClient(app) as admin:
            token = _login_admin(admin)
            refused = admin.post(
                _PATH,
                json=_body("q-http-pub-one", "a-http-pub-one"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(refused.status_code, 409)
        body = refused.json()
        self.assertEqual(body["code"], "not_approved")
        self.assertTrue(body["message"])
        self.assertTrue(body["request_id"])
        self.assertEqual(app.state.loop.publications.rows_for("q-http-pub-one", "a-http-pub-one"), ())
        audit = [row for row in app.state.loop.identity.audits.rows if row.action == "publication_published"]
        self.assertEqual(audit, [])

    def test_http_publish_is_idempotent_when_already_active(self) -> None:
        app = _app()
        question_id, answer_id = "q-http-pub-again", "a-http-pub-again"
        _approve(app, question_id, answer_id)
        with TestClient(app) as admin:
            token = _login_admin(admin)
            first = admin.post(_PATH, json=_body(question_id, answer_id), headers={"X-K12-CSRF": token})
            second = admin.post(
                _PATH,
                json=_body(question_id, answer_id, layout_template_id="later"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["outcome"], "published")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json(), {"outcome": "already_active"})
        rows = app.state.loop.publications.rows_for(question_id, answer_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "active")
        self.assertIsNone(rows[0].layout_template_id)
        audit = [row for row in app.state.loop.identity.audits.rows if row.action == "publication_published"]
        self.assertEqual(len(audit), 1)

    def test_http_publish_after_retire_creates_new_active(self) -> None:
        app = _app()
        question_id, answer_id = "q-http-pub-seq", "a-http-pub-seq"
        _approve(app, question_id, answer_id, subject_id="geom-seq")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            headers = {"X-K12-CSRF": token}
            first = admin.post(_PATH, json=_body(question_id, answer_id), headers=headers)
            retired = admin.post(_RETIRE, json=_body(question_id, answer_id), headers=headers)
            second = admin.post(_PATH, json=_body(question_id, answer_id), headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json(), {"outcome": "retired"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(
            first.json(),
            {"outcome": "published", "publication_id": f"pub-{question_id}-{answer_id}-1"},
        )
        self.assertEqual(
            second.json(),
            {"outcome": "published", "publication_id": f"pub-{question_id}-{answer_id}-2"},
        )
        rows = {row.status: row for row in app.state.loop.publications.rows_for(question_id, answer_id)}
        self.assertEqual(set(rows), {"retired", "active"})
        self.assertEqual(rows["retired"].publication_id, f"pub-{question_id}-{answer_id}-1")
        self.assertEqual(rows["active"].publication_id, f"pub-{question_id}-{answer_id}-2")
        audit = [row for row in app.state.loop.identity.audits.rows if row.action == "publication_published"]
        self.assertEqual(len(audit), 2)
        sequences = [json.loads(row.detail_json)["sequence"] for row in audit]
        self.assertEqual(sequences, [1, 2])


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


def _approve(
    app: object,
    question_id: str,
    answer_id: str,
    *,
    subject_id: str = "math",
    answer_approved: bool = True,
) -> None:
    app.state.loop.approvals.put(  # type: ignore[attr-defined]
        ApprovalSnapshot(
            question_version_id=question_id,
            answer_version_id=answer_id,
            asset_ids=(),
            layout_template_id="layout-none",
            question_approved=True,
            answer_approved=answer_approved,
            retired=False,
            subject_id=subject_id,
            item_order=("sq-1",),
            stem=_STEM,
            answer_text="2",
        )
    )


def _body(question_id: str, answer_id: str, layout_template_id: str | None = None) -> dict[str, str]:
    body = {"question_version_id": question_id, "answer_version_id": answer_id}
    if layout_template_id is not None:
        body["layout_template_id"] = layout_template_id
    return body
