"""An issued face may show the printed student number. Audit, logs, and webhooks must not."""

from __future__ import annotations

import json
import os
import threading
import unittest
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.identity.domain.records import Grant, Student
from backend.practice.adapters.memory import MemoryPractice

BAIT_ID = "synth-leak-r4"
BAIT_NAME = "synth-name-r4"
STUDENT_ID = "student-leak-r4"
ISSUE = {
    "student_id": STUDENT_ID,
    "subject_id": "math",
    "question_version_id": "q-v1",
    "review_version_id": "rev-1",
}


class PaperFaceBoundaryTest(unittest.TestCase):
    def test_audit_detail_omits_external_id_after_issue(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login_teacher(client)
            _plant(app)
            _publish(client, token)
            issued = client.post("/api/practice/papers", json=ISSUE, headers=_csrf(token))
            self.assertEqual(issued.status_code, 200, issued.text)
            self.assertNotIn(BAIT_ID, issued.text)
            self.assertNotIn(BAIT_NAME, issued.text)
            pdf = client.get("/api/practice/files/" + issued.json()["file_id"]).content
        self.assertIn(BAIT_ID.encode(), pdf)
        self.assertNotIn(BAIT_NAME.encode(), pdf)
        self.assertNotIn(STUDENT_ID.encode(), pdf)
        text = _audit_text(app)
        self.assertIn("login", text)
        self.assertNotIn(BAIT_ID, text)
        self.assertNotIn(BAIT_NAME, text)
        self.assertNotIn("api_key", text.lower())

    def test_error_webhook_body_omits_external_id(self) -> None:
        server = _listen()
        app = _app()
        try:
            with mock.patch.dict(os.environ, _quiet_proxy(_url(server))):
                with TestClient(app) as client:
                    token = _login_teacher(client)
                    _plant(app)
                    _publish(client, token)
                    with mock.patch.object(MemoryPractice, "place_issued", side_effect=RuntimeError("forced-store")):
                        failed = client.post("/api/practice/papers", json=ISSUE, headers=_csrf(token))
                    app.state.errors.wait()  # type: ignore[attr-defined]
            self.assertEqual(failed.status_code, 409)
            self.assertNotIn(BAIT_ID, failed.text)
            self.assertNotIn(BAIT_NAME, failed.text)
            self.assertEqual(server.hits, 1)  # type: ignore[attr-defined]
            body = json.loads(server.received[0].decode("utf-8"))  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(set(body), {"time", "request_id", "module", "event", "outcome"})
        self.assertEqual(body["event"], "use_case_failed")
        dumped = json.dumps(body)
        self.assertNotIn(BAIT_ID, dumped)
        self.assertNotIn(BAIT_NAME, dumped)
        self.assertNotIn("api_key", dumped.lower())

    def test_log_capture_omits_external_id(self) -> None:
        app = _app()
        buffer = StringIO()
        with TestClient(app) as client:
            token = _login_teacher(client)
            _plant(app)
            _publish(client, token)
            with redirect_stdout(buffer):
                issued = client.post("/api/practice/papers", json=ISSUE, headers=_csrf(token))
                self.assertEqual(issued.status_code, 200, issued.text)
        text = buffer.getvalue()
        self.assertIn("paper_created", text)
        self.assertNotIn(BAIT_ID, text)
        self.assertNotIn(BAIT_NAME, text)
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
        "K12_PAPER_QR": "on",
    }


def _app() -> object:
    with mock.patch.dict(os.environ, {"K12_LOG_FILE": "0", "K12_PAPER_QR": "on"}):
        return create_app(seed=True)


def _login_teacher(client: TestClient) -> str:
    response = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.text)
    return str(response.json()["csrf_token"])


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


def _publish(client: TestClient, token: str) -> None:
    response = client.post("/api/catalog/q-v1/publish", headers=_csrf(token))
    if response.status_code != 200:
        raise AssertionError(response.text)


def _plant(app: object) -> None:
    identity = app.state.loop.identity  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    identity.students.insert(
        Student(
            student_id=STUDENT_ID,
            external_id=BAIT_ID,
            name=BAIT_NAME,
            grade="g7",
            subject_id="math",
            status="active",
            created_by=ACTOR_TEACHER_ID,
            created_at=now,
            updated_at=now,
        )
    )
    identity.grants.insert(
        Grant(
            grant_id=str(uuid.uuid4()),
            teacher_id=ACTOR_TEACHER_ID,
            student_id=STUDENT_ID,
            subject_id="math",
            granted_by=ACTOR_TEACHER_ID,
            granted_at=now,
        )
    )


def _audit_text(app: object) -> str:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    parts: list[str] = []
    for row in book.rows:
        parts.append(" ".join((row.action, row.target_id, row.detail_json, row.outcome)))
    for event in book.events:
        parts.append(json.dumps(event.fields(), ensure_ascii=False))
    return "\n".join(parts)
