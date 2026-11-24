"""Imported review drafts do not put student numbers, names, or keys into audit, logs, or webhooks."""

from __future__ import annotations

import json
import os
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.catalog.adapters.draft_memory import MemoryDrafts

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
BAIT_ID = "synth-leak-r3"
BAIT_NAME = "synth-name-r3"


class CatalogImportBoundaryTest(unittest.TestCase):
    def test_audit_detail_omits_external_id_after_import(self) -> None:
        app = _app()
        with TestClient(app) as admin:
            token = _login_admin(admin)
            bait = admin.post(_IMPORT, json=_bait(), headers=_csrf(token))
            self.assertEqual(bait.status_code, 200, bait.text)
            self.assertEqual(bait.json()["reason"], "unknown_field")
            self.assertNotIn(BAIT_ID, bait.text)
            self.assertNotIn(BAIT_NAME, bait.text)
            created = admin.post(_IMPORT, json=_body(), headers=_csrf(token))
            self.assertEqual(created.status_code, 200, created.text)
        text = _audit_text(app)
        self.assertIn("import_book", text)
        self.assertNotIn("import_review", text)
        self.assertNotIn(BAIT_ID, text)
        self.assertNotIn(BAIT_NAME, text)
        self.assertNotIn("计算", text)

    def test_error_webhook_body_omits_external_id(self) -> None:
        server = _listen()
        app = _app()
        try:
            with mock.patch.dict(os.environ, _quiet_proxy(_url(server))):
                with TestClient(app) as admin:
                    token = _login_admin(admin)
                    with mock.patch.object(MemoryDrafts, "save", side_effect=RuntimeError("forced-store")):
                        failed = admin.post(_IMPORT, json=_body(), headers=_csrf(token))
                    app.state.errors.wait()  # type: ignore[attr-defined]
            self.assertEqual(failed.status_code, 409)
            self.assertNotIn(BAIT_ID, failed.text)
            self.assertNotIn(BAIT_NAME, failed.text)
            self.assertNotIn("计算", failed.text)
            self.assertEqual(server.hits, 1)  # type: ignore[attr-defined]
            body = json.loads(server.received[0].decode("utf-8"))  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(set(body), {"time", "request_id", "module", "event", "outcome"})
        self.assertEqual(body["event"], "use_case_failed")
        self.assertNotIn(BAIT_ID, json.dumps(body))
        self.assertNotIn(BAIT_NAME, json.dumps(body))

    def test_log_capture_omits_external_id(self) -> None:
        app = _app()
        buffer = StringIO()
        with TestClient(app) as admin:
            token = _login_admin(admin)
            with redirect_stdout(buffer):
                created = admin.post(_IMPORT, json=_body(), headers=_csrf(token))
                self.assertEqual(created.status_code, 200, created.text)
        text = buffer.getvalue()
        self.assertNotIn(BAIT_ID, text)
        self.assertNotIn(BAIT_NAME, text)
        self.assertNotIn("计算", text)
        self.assertNotIn("api_key", text.lower())


class _Hook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        self.server.received.append(payload)  # type: ignore[attr-defined]
        self.server.hits += 1  # type: ignore[attr-defined]
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def _listen() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Hook)
    server.received = []  # type: ignore[attr-defined]
    server.hits = 0  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.thread = thread  # type: ignore[attr-defined]
    thread.start()
    return server


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.thread.join(2)  # type: ignore[attr-defined]
    server.server_close()


def _url(server: ThreadingHTTPServer) -> str:
    return "http://127.0.0.1:" + str(server.server_address[1]) + "/hook"


def _quiet_proxy(url: str) -> dict[str, str]:
    return {
        "K12_ERROR_WEBHOOK_URL": url,
        "NO_PROXY": "127.0.0.1",
        "no_proxy": "127.0.0.1",
    }


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
    response = client.post("/api/login", json={"username": ADMIN_USER, "secret": ADMIN_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.text)
    token = response.json()["csrf_token"]
    changed = client.post(
        "/api/account/password",
        json={"old_secret": ADMIN_SECRET, "new_secret": ADMIN_NEXT},
        headers={"X-K12-CSRF": token},
    )
    if changed.status_code != 200:
        raise AssertionError(changed.text)
    return token


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


_IMPORT = "/api/admin/catalog/books/synth-r3/import"


def _body() -> dict[str, object]:
    return {
        "subject_id": "math",
        "dry_run": False,
        "pairing": [],
        "pages": [
            {
                "pdf_page": 1,
                "role": "questions",
                "questions": {
                    "contract": "k12-question-draft",
                    "contract_version": 1,
                    "schema_version": 1,
                    "ok": True,
                    "reason": "",
                    "preface": "",
                    "source": {"pdf_page": 1},
                    "questions": [
                        {
                            "key": "r3:1",
                            "section": "一",
                            "number": "1",
                            "type": "single_choice",
                            "structure": "choice",
                            "status": "confirmed",
                            "stem": [{"type": "text", "value": "计算："}, {"type": "math", "latex": "(-3)+5"}],
                            "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
                            "subquestions": [],
                            "assets": [],
                            "geometry": None,
                        }
                    ],
                },
                "answers": [
                    {
                        "contract": "k12-answer-draft",
                        "contract_version": 1,
                        "schema_version": 1,
                        "ok": True,
                        "reason": "",
                        "question_key": "r3:1",
                        "key": "r3:1:ocr:1",
                        "origin": "ocr",
                        "status": "confirmed",
                        "applicable": True,
                        "source": {"pdf_page": 1},
                        "content": [{"type": "text", "value": "2"}],
                        "parts": [],
                        "assets": [],
                    }
                ],
            }
        ],
    }


def _bait() -> dict[str, object]:
    body = _body()
    body["external_id"] = BAIT_ID
    body["name"] = BAIT_NAME
    return body


def _audit_text(app: object) -> str:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    parts: list[str] = []
    for row in book.rows:
        parts.append(" ".join((row.action, row.target_id, row.detail_json, row.outcome)))
    for event in book.events:
        parts.append(json.dumps(event.fields(), ensure_ascii=False))
    return "\n".join(parts)
