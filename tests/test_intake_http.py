"""Intake photos stay with the issuing teacher. Logs do not carry the student number or the bytes."""

from __future__ import annotations

import json
import os
import threading
import unittest
import uuid
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.identity.domain.records import Grant, Student
from backend.practice.adapters.memory_intake import MemoryIntake
from backend.practice.domain.qr_code import qr_payload

BAIT_ID = "bait-r5-ext"
BAIT_NAME = "bait-r5-name"
STUDENT_ID = "student-r5-bait"
MARKER = b"EXIF-MARKER-SYNTH"
APP13 = b"APP13-MARKER-SYNTH"
PIXELS = b"IMAGE-BYTES-SYNTH"


class IntakeHttpTest(unittest.TestCase):
    def test_issuing_teacher_stores_intake_and_the_page_is_received(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            paper_id = opened["paper_id"]
            listed = client.get("/api/practice/papers")
            row = listed.json()["papers"][0]
            self.assertEqual(row["printed_external_id"], BAIT_ID)
            self.assertEqual(row["page_count"], 1)
            self.assertRegex(row["issued_on"], r"^\d{4}-\d{2}-\d{2}$")
            uploaded = _put(client, token, paper_id, 1, _jpeg(), located_by="qr", qr=qr_payload(paper_id, 1))
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            body = uploaded.json()
            self.assertEqual(body["located_by"], "qr")
            self.assertFalse(body["replaced"])
            self.assertNotIn(BAIT_ID, uploaded.text)
            stored = app.state.loop.files.read(body["file_id"])
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertNotIn(MARKER, stored)
            self.assertNotIn(APP13, stored)
            self.assertIn(PIXELS, stored)
            self.assertTrue(stored.startswith(b"\xff\xd8"))
            status = client.get("/api/practice/papers/" + paper_id + "/intake")
            self.assertEqual(status.status_code, 200, status.text)
            page = status.json()["pages"][0]
            self.assertTrue(page["received"])
            self.assertEqual(page["located_by"], "qr")
            self.assertEqual(page["intake_id"], body["intake_id"])
            self.assertNotIn(BAIT_ID, status.text)
            image = client.get("/api/practice/intake/" + body["intake_id"] + "/image")
            again = client.get("/api/practice/intake/" + body["intake_id"] + "/image")
        self.assertEqual(image.status_code, 200, image.text)
        self.assertEqual(image.headers["cache-control"], "no-store")
        self.assertEqual(image.content, stored)
        self.assertNotIn(BAIT_ID.encode(), image.content)
        reads = [event for event in app.state.loop.identity.audits.events if event.event == "intake_read"]
        self.assertEqual(len(reads), 2)
        uploaded_audit = [event for event in app.state.loop.identity.audits.events if event.event == "intake_uploaded"]
        self.assertEqual(len(uploaded_audit), 1)
        detail = json.loads(uploaded_audit[0].detail)
        self.assertEqual(detail["paper_id"], paper_id)
        self.assertEqual(detail["page_no"], 1)
        self.assertEqual(detail["located_by"], "qr")
        self.assertFalse(detail["replaced"])
        text = _audit_text(app)
        self.assertNotIn(BAIT_ID, text)
        self.assertNotIn(BAIT_NAME, text)
        self.assertNotIn(PIXELS.decode("ascii"), text)
        self.assertNotIn(MARKER.decode("ascii"), text)

    def test_another_teacher_student_and_anonymous_are_refused(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            paper_id = opened["paper_id"]
            uploaded = _put(client, token, paper_id, 1, _jpeg(), located_by="manual")
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            intake_id = uploaded.json()["intake_id"]
            client.post("/api/logout", headers=_csrf(token))
            _copy_user(app, "teacher-other-r5", "teacher")
            other = _login(client, "teacher-other-r5")
            refused = _put(client, other, paper_id, 1, _jpeg(), located_by="manual")
            hidden = client.get("/api/practice/papers/" + paper_id + "/intake")
            image = client.get("/api/practice/intake/" + intake_id + "/image")
            self.assertEqual(refused.status_code, 403)
            self.assertEqual(refused.json()["code"], "permission_denied")
            self.assertEqual(hidden.status_code, 403)
            self.assertEqual(image.status_code, 403)
            self.assertEqual(app.state.loop.intake.count(), 1)
            client.post("/api/logout", headers=_csrf(other))
            _copy_user(app, "student-r5", "student")
            student = _login(client, "student-r5")
            student_put = _put(client, student, paper_id, 1, _jpeg(), located_by="manual")
            student_image = client.get("/api/practice/intake/" + intake_id + "/image")
            self.assertEqual(student_put.status_code, 403)
            self.assertEqual(student_put.json()["code"], "permission_denied")
            self.assertEqual(student_image.status_code, 403)
            client.post("/api/logout", headers=_csrf(student))
            anonymous = client.put(
                "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
                content=_jpeg(),
                headers={"Content-Type": "image/jpeg"},
            )
            self.assertEqual(anonymous.status_code, 401)
            self.assertEqual(anonymous.json()["code"], "unauthenticated")

    def test_admin_can_read_and_a_missing_csrf_writes_nothing(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            paper_id = opened["paper_id"]
            missing = client.put(
                "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
                content=_jpeg(),
                headers={"Content-Type": "image/jpeg"},
            )
            self.assertEqual(missing.status_code, 403)
            self.assertEqual(missing.json()["code"], "csrf")
            self.assertEqual(app.state.loop.intake.count(), 0)
            uploaded = _put(client, token, paper_id, 1, _jpeg(), located_by="manual")
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            client.post("/api/logout", headers=_csrf(token))
            admin = _login(client, ACTOR_ADMIN_ID)
            image = client.get("/api/practice/intake/" + uploaded.json()["intake_id"] + "/image")
            status = client.get("/api/practice/papers/" + paper_id + "/intake")
        self.assertEqual(image.status_code, 200, image.content[:2])
        self.assertEqual(status.status_code, 200, status.text)
        self.assertNotIn(BAIT_ID, status.text)

    def test_bad_inputs_write_no_row(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            paper_id = opened["paper_id"]
            cases = [
                _put(client, token, paper_id, 9, _jpeg(), located_by="manual"),
                _put(client, token, "missing-paper-r5", 1, _jpeg(), located_by="manual"),
                _put(client, token, paper_id, 1, _jpeg(), located_by="qr", qr="not-this-paper#1"),
                _put(client, token, paper_id, 1, b"not-an-image", located_by="manual"),
            ]
            self.assertEqual([item.json()["code"] for item in cases], [
                "page_out_of_range",
                "paper_not_found",
                "qr_mismatch",
                "not_image",
            ])
            self.assertEqual(app.state.loop.intake.count(), 0)
            with mock.patch.dict(os.environ, {"K12_INTAKE_MAX_BYTES": "32"}):
                huge = _put(client, token, paper_id, 1, _jpeg(), located_by="manual")
            self.assertEqual(huge.status_code, 413)
            self.assertEqual(huge.json()["code"], "too_large")
            self.assertEqual(app.state.loop.intake.count(), 0)
            self.assertNotIn(BAIT_ID, huge.text)

    def test_replace_keeps_one_current_row_and_the_old_file(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            paper_id = opened["paper_id"]
            first = _put(client, token, paper_id, 1, _jpeg(), located_by="manual")
            self.assertEqual(first.status_code, 200, first.text)
            again = _put(client, token, paper_id, 1, _jpeg(extra=b"SECOND"), located_by="manual")
            self.assertEqual(again.status_code, 409)
            self.assertEqual(again.json()["code"], "page_already_received")
            self.assertEqual(app.state.loop.intake.count(), 1)
            replaced = _put(
                client, token, paper_id, 1, _jpeg(extra=b"SECOND"), located_by="manual", replace="true"
            )
            self.assertEqual(replaced.status_code, 200, replaced.text)
            self.assertTrue(replaced.json()["replaced"])
            old = app.state.loop.intake.get(first.json()["intake_id"])
            current = app.state.loop.intake.current(paper_id, 1)
        self.assertIsNotNone(old.superseded_at)
        self.assertEqual(current.intake_id, replaced.json()["intake_id"])
        self.assertIsNone(current.superseded_at)
        self.assertEqual(app.state.loop.intake.count(), 2)
        self.assertEqual(len(app.state.loop.intake.currents(paper_id)), 1)
        self.assertIsNotNone(app.state.loop.files.read(old.file_id))

    def test_a_photo_over_one_mebibyte_is_not_the_json_limit(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            uploaded = _put(client, token, opened["paper_id"], 1, _jpeg(extra=b"Z" * 1_200_000), located_by="manual")
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertNotEqual(uploaded.json().get("code"), "payload_too_large")

    def test_publication_asset_rejects_an_intake_file(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            opened = _issue(client, token)
            uploaded = _put(client, token, opened["paper_id"], 1, _jpeg(), located_by="manual")
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            file_id = uploaded.json()["file_id"]
            app.state.loop.publications.note_intake_file(file_id)
            client.post("/api/logout", headers=_csrf(token))
            admin = _login(client, ACTOR_ADMIN_ID)
            _publish_asset_target(app)
            refused = client.post(
                "/api/admin/publications/pub-r5-intake/assets",
                json={
                    "file_id": file_id,
                    "kind": "image",
                    "checksum": "checksum-r5-intake",
                    "size_bytes": 8,
                    "mime_type": "image/jpeg",
                },
                headers=_csrf(admin),
            )
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()["result"], "intake_file_rejected")

    def test_log_and_webhook_omit_the_student_number_and_the_bytes(self) -> None:
        server = _listen()
        app = _app()
        buffer = StringIO()
        try:
            with mock.patch.dict(os.environ, _quiet_proxy(_url(server))):
                with TestClient(app) as client:
                    token = _login(client, ACTOR_TEACHER_ID)
                    _plant(app)
                    opened = _issue(client, token)
                    with redirect_stdout(buffer):
                        uploaded = _put(
                            client,
                            token,
                            opened["paper_id"],
                            1,
                            _jpeg(),
                            located_by="manual",
                        )
                    self.assertEqual(uploaded.status_code, 200, uploaded.text)
                    with mock.patch.object(MemoryIntake, "place", side_effect=RuntimeError("forced-store")):
                        with redirect_stdout(buffer):
                            failed = _put(
                                client,
                                token,
                                opened["paper_id"],
                                1,
                                _jpeg(extra=b"SECOND"),
                                located_by="manual",
                                replace="true",
                            )
                    app.state.errors.wait()  # type: ignore[attr-defined]
            self.assertEqual(failed.status_code, 409)
            self.assertEqual(failed.json()["code"], "store_failed")
            self.assertNotIn(BAIT_ID, failed.text)
            self.assertEqual(server.hits, 1)  # type: ignore[attr-defined]
            body = json.loads(server.received[0].decode("utf-8"))  # type: ignore[attr-defined]
        finally:
            _stop(server)
        text = buffer.getvalue()
        self.assertIn("http_completed", text)
        self.assertNotIn(BAIT_ID, text)
        self.assertNotIn(BAIT_NAME, text)
        self.assertNotIn(PIXELS.decode("ascii"), text)
        self.assertNotIn(MARKER.decode("ascii"), text)
        self.assertEqual(set(body), {"time", "request_id", "module", "event", "outcome"})
        self.assertEqual(body["event"], "use_case_failed")
        dumped = json.dumps(body)
        self.assertNotIn(BAIT_ID, dumped)
        self.assertNotIn(BAIT_NAME, dumped)
        self.assertNotIn(PIXELS.decode("ascii"), dumped)
        self.assertNotIn(MARKER.decode("ascii"), dumped)
        audit = _audit_text(app)
        self.assertNotIn(BAIT_ID, audit)
        self.assertNotIn(PIXELS.decode("ascii"), audit)
        self.assertNotIn(MARKER.decode("ascii"), audit)


def _jpeg(extra: bytes = b"") -> bytes:
    def segment(marker: int, payload: bytes) -> bytes:
        length = len(payload) + 2
        return bytes((0xFF, marker, (length >> 8) & 0xFF, length & 0xFF)) + payload

    return (
        b"\xff\xd8"
        + segment(0xE1, MARKER)
        + segment(0xED, APP13)
        + segment(0xDA, b"")
        + PIXELS
        + extra
        + b"\xff\xd9"
    )


def _app() -> object:
    # A set DSN skips the memory smoke admin. These cases stay in memory.
    with mock.patch.dict(os.environ, {"K12_LOG_FILE": "0", "K12_PAPER_QR": "on", "K12_PG_DSN": ""}):
        return create_app(seed=True)


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/login", json={"username": username, "secret": SYNTH_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.text)
    return str(response.json()["csrf_token"])


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


def _issue(client: TestClient, token: str) -> dict[str, object]:
    published = client.post("/api/catalog/q-v1/publish", headers=_csrf(token))
    if published.status_code != 200:
        raise AssertionError(published.text)
    opened = client.post(
        "/api/practice/papers",
        json={
            "student_id": STUDENT_ID,
            "subject_id": "math",
            "question_version_id": "q-v1",
            "review_version_id": "rev-1",
        },
        headers=_csrf(token),
    )
    if opened.status_code != 200:
        raise AssertionError(opened.text)
    return opened.json()


def _put(client: TestClient, token: str, paper_id: str, page: int, body: bytes, **query: str) -> object:
    headers = {"Content-Type": "image/jpeg"}
    if token:
        headers["X-K12-CSRF"] = token
    qr = query.pop("qr", "")
    if qr:
        headers["X-K12-Qr"] = qr
    target = "/api/practice/papers/" + paper_id + "/pages/" + str(page) + "/intake"
    if query:
        target += "?" + "&".join(key + "=" + value for key, value in query.items())
    return client.put(target, content=body, headers=headers)


def _plant(app: object) -> None:
    identity = app.state.loop.identity  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    if identity.students.by_id(STUDENT_ID) is None:
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


def _copy_user(app: object, username: str, role: str) -> None:
    users = app.state.loop.identity.users  # type: ignore[attr-defined]
    teacher = users.by_username(ACTOR_TEACHER_ID)
    users.insert(replace(teacher, user_id=username, username=username, role=role))


def _publish_asset_target(app: object) -> None:
    from backend.catalog.domain.publication import Publication

    app.state.loop.publications.put(  # type: ignore[attr-defined]
        Publication(
            publication_id="pub-r5-intake",
            question_version_id="q-r5-intake",
            answer_version_id="a-r5-intake",
            subject_id="math",
            status="active",
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


class _Hook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.server.received.append(self.rfile.read(length))  # type: ignore[attr-defined]
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


class HttpHostTest(unittest.TestCase):
    def test_http_host_defaults_and_reads_the_environment(self) -> None:
        from backend.bootstrap.run_mode import http_host

        with mock.patch.dict(os.environ, {"K12_HTTP_HOST": ""}, clear=False):
            os.environ.pop("K12_HTTP_HOST", None)
            self.assertEqual(http_host(), "127.0.0.1")
        with mock.patch.dict(os.environ, {"K12_HTTP_HOST": "  "}):
            self.assertEqual(http_host(), "127.0.0.1")
        with mock.patch.dict(os.environ, {"K12_HTTP_HOST": "0.0.0.0"}):
            self.assertEqual(http_host(), "0.0.0.0")


def _quiet_proxy(url: str) -> dict[str, str]:
    return {
        "K12_ERROR_WEBHOOK_URL": url,
        "NO_PROXY": "127.0.0.1",
        "no_proxy": "127.0.0.1",
        "K12_LOG_FILE": "0",
        "K12_PAPER_QR": "on",
    }
