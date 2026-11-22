"""HTTP attach, remove, and list for publication assets."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.catalog.domain.publication import Publication, asset_id_for

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
_FILE = "pubfile-0123456789abcdef"
_BODY = {
    "file_id": _FILE,
    "kind": "image",
    "checksum": "checksum-http",
    "size_bytes": 16,
    "mime_type": "image/png",
}


class PublicationAssetHttpTest(unittest.TestCase):
    def test_http_assets_reject_unauthenticated(self) -> None:
        app = _app()
        with TestClient(app) as anon:
            posted = anon.post(_assets("pub-http-anon"), json=_BODY)
            deleted = anon.delete(_asset("pub-http-anon", "pubasset-0123456789abcdef"))
            listed = anon.get(_assets("pub-http-anon"))
        for response in (posted, deleted, listed):
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["code"], "unauthenticated")
            self.assertTrue(response.json()["request_id"])

    def test_http_assets_reject_teacher(self) -> None:
        app = _app()
        _put(app, "pub-http-teacher")
        with TestClient(app) as teacher:
            token = _login(teacher, ACTOR_TEACHER_ID, SYNTH_SECRET)
            header = {"X-K12-CSRF": token}
            posted = teacher.post(_assets("pub-http-teacher"), json=_BODY, headers=header)
            deleted = teacher.delete(_asset("pub-http-teacher", "pubasset-0123456789abcdef"), headers=header)
            listed = teacher.get(_assets("pub-http-teacher"))
        for response in (posted, deleted, listed):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "permission_denied")

    def test_http_post_attaches_for_admin(self) -> None:
        app = _app()
        _put(app, "pub-http-ok")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            attached = admin.post(_assets("pub-http-ok"), json=_BODY, headers={"X-K12-CSRF": token})
        self.assertIn(attached.status_code, (200, 201), attached.text)
        self.assertEqual(attached.status_code, 201)
        body = attached.json()
        self.assertEqual(body["result"], "attached")
        self.assertEqual(body["publication_asset_id"], asset_id_for("pub-http-ok", "checksum-http"))

    def test_http_post_rejects_invalid_body(self) -> None:
        app = _app()
        _put(app, "pub-http-body")
        payload = {"file_id": _FILE, "kind": "image", "size_bytes": 1, "mime_type": "image/png"}
        with TestClient(app) as admin:
            token = _login_admin(admin)
            refused = admin.post(_assets("pub-http-body"), json=payload, headers={"X-K12-CSRF": token})
        self.assertEqual(refused.status_code, 422)

    def test_http_post_maps_page_file_rejected(self) -> None:
        app = _app()
        _put(app, "pub-http-page")
        payload = dict(_BODY)
        payload["file_id"] = "file-0123456789abcdef"
        payload["checksum"] = "checksum-http-page"
        with TestClient(app) as admin:
            token = _login_admin(admin)
            refused = admin.post(_assets("pub-http-page"), json=payload, headers={"X-K12-CSRF": token})
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()["result"], "page_file_rejected")

    def test_http_delete_removes_for_admin(self) -> None:
        app = _app()
        _put(app, "pub-http-del")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            header = {"X-K12-CSRF": token}
            attached = admin.post(_assets("pub-http-del"), json=_BODY, headers=header)
            asset_id = attached.json()["publication_asset_id"]
            removed = admin.delete(_asset("pub-http-del", asset_id), headers=header)
            listed = admin.get(_assets("pub-http-del"))
        self.assertEqual(attached.status_code, 201, attached.text)
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json(), {"result": "removed"})
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"], [])

    def test_http_delete_missing_is_404(self) -> None:
        app = _app()
        _put(app, "pub-http-miss")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            missing = admin.delete(
                _asset("pub-http-miss", "pubasset-0123456789abcdef"),
                headers={"X-K12-CSRF": token},
            )
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["result"], "not_found")

    def test_http_get_returns_items(self) -> None:
        app = _app()
        _put(app, "pub-http-list")
        with TestClient(app) as admin:
            token = _login_admin(admin)
            admin.post(
                _assets("pub-http-list"),
                json=_BODY,
                headers={"X-K12-CSRF": token},
            )
            listed = admin.get(_assets("pub-http-list"))
        self.assertEqual(listed.status_code, 200, listed.text)
        items = listed.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["publication_id"], "pub-http-list")
        self.assertEqual(items[0]["file_id"], _FILE)
        self.assertEqual(items[0]["kind"], "image")
        self.assertEqual(items[0]["checksum"], "checksum-http")
        self.assertEqual(items[0]["size_bytes"], 16)
        self.assertEqual(items[0]["mime_type"], "image/png")
        self.assertTrue(items[0]["created_by"])
        self.assertTrue(items[0]["created_at"])


def _assets(publication_id: str) -> str:
    return f"/api/admin/publications/{publication_id}/assets"


def _asset(publication_id: str, publication_asset_id: str) -> str:
    return f"/api/admin/publications/{publication_id}/assets/{publication_asset_id}"


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


def _put(app: object, publication_id: str) -> None:
    app.state.loop.publications.put(  # type: ignore[attr-defined]
        Publication(
            publication_id=publication_id,
            question_version_id=f"q-{publication_id}",
            answer_version_id=f"a-{publication_id}",
            subject_id="subj-http-d8a",
            status="active",
        )
    )
