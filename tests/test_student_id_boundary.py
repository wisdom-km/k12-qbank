"""Student numbers stay out of audit detail, logs, and the error webhook."""

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
from backend.identity.adapters.memory import MemoryStudents

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"


class StudentIdBoundaryTest(unittest.TestCase):
    def test_audit_detail_omits_external_id_after_create_and_update(self) -> None:
        created_id = "synth-leak-0001"
        updated_id = "synth-leak-0002"
        app = _app()
        with TestClient(app) as admin:
            token = _login_admin(admin)
            created = admin.post("/api/admin/students", json=_body(created_id), headers=_csrf(token))
            self.assertEqual(created.status_code, 200, created.text)
            student_id = created.json()["student_id"]
            changed = admin.post(
                "/api/admin/students/" + student_id,
                json=_body(updated_id),
                headers=_csrf(token),
            )
            self.assertEqual(changed.status_code, 200, changed.text)
        text = _audit_text(app)
        self.assertIn("create_student", text)
        self.assertIn("update_student", text)
        self.assertIn(student_id, text)
        self.assertNotIn(created_id, text)
        self.assertNotIn(updated_id, text)

    def test_error_webhook_body_omits_external_id(self) -> None:
        external_id = "synth-leak-0003"
        server = _listen()
        app = _app()
        try:
            with mock.patch.dict(os.environ, _quiet_proxy(_url(server))):
                with TestClient(app) as admin:
                    token = _login_admin(admin)
                    with mock.patch.object(MemoryStudents, "insert", side_effect=RuntimeError("forced-store")):
                        failed = admin.post("/api/admin/students", json=_body(external_id), headers=_csrf(token))
                    app.state.errors.wait()  # type: ignore[attr-defined]
            self.assertEqual(failed.status_code, 409)
            self.assertNotIn(external_id, failed.text)
            self.assertEqual(server.hits, 1)  # type: ignore[attr-defined]
            body = json.loads(server.received[0].decode("utf-8"))  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(set(body), {"time", "request_id", "module", "event", "outcome"})
        self.assertEqual(body["event"], "use_case_failed")
        self.assertNotIn(external_id, json.dumps(body))

    def test_log_capture_omits_external_id(self) -> None:
        created_id = "synth-leak-0004"
        updated_id = "synth-leak-0005"
        app = _app()
        buffer = StringIO()
        with TestClient(app) as admin:
            token = _login_admin(admin)
            with redirect_stdout(buffer):
                created = admin.post("/api/admin/students", json=_body(created_id), headers=_csrf(token))
                self.assertEqual(created.status_code, 200, created.text)
                student_id = created.json()["student_id"]
                changed = admin.post(
                    "/api/admin/students/" + student_id,
                    json=_body(updated_id),
                    headers=_csrf(token),
                )
                self.assertEqual(changed.status_code, 200, changed.text)
        logged = [
            json.dumps(event.fields(), ensure_ascii=False)
            for event in app.state.loop.identity.audits.events  # type: ignore[attr-defined]
        ]
        blob = buffer.getvalue() + "\n" + "\n".join(logged)
        self.assertTrue(any("create_student" in line for line in logged))
        self.assertNotIn(created_id, blob)
        self.assertNotIn(updated_id, blob)


class _Hook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.received.append(raw)  # type: ignore[attr-defined]
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


def _body(external_id: str) -> dict[str, str]:
    return {"external_id": external_id, "grade": "g7", "subject_id": "math"}


def _audit_text(app: object) -> str:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    parts: list[str] = []
    for row in book.rows:
        parts.append(" ".join((row.action, row.target_id, row.detail_json)))
    for event in book.events:
        parts.append(event.detail)
    return "\n".join(parts)
