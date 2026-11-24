"""Recognition HTTP stays on the mock. A failed run does not block confirm."""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
import uuid
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

from fastapi.testclient import TestClient

from backend.ai.adapters.memory_runs import MemoryRuns
from backend.ai.adapters.mock_model import MockModel
from backend.ai.application.recognize import captured_judge, captured_transcribe
from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.identity.domain.records import Grant, Student
from backend.practice.domain.item import ItemBox, PracticeItem

BAIT_ID = "synth-bait-ext"
BAIT_NAME = "name-bait-r6"
STUDENT_ID = "student-hidden-r6"
PIXELS = b"IMAGE-BYTES-R6"
PROMPT_MARK = "不要判断对错"
PROBE = "probe-key"
TRANSCRIPTION = "ans-bait-r6"


class AiHttpTest(unittest.TestCase):
    def test_teacher_starts_and_lists_suggestions(self) -> None:
        app = _app()
        model = MockModel(transcription="A")
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            opened = _ready(app, client, token)
            paper_id = str(opened["paper_id"])
            _items(app, paper_id)
            uploaded = _put(client, token, paper_id)
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            intake_id = uploaded.json()["intake_id"]
            app.state.loop = replace(app.state.loop, model=model)
            started = client.post(_start(intake_id), json={}, headers=_csrf(token))
            self.assertEqual(started.status_code, 202, started.text)
            self.assertEqual(started.json()["status"], "queued")
            run_id = started.json()["run_id"]
            done = _wait(client, run_id)
            body = done.json()
            self.assertEqual(body["status"], "succeeded", body)
            by_order = {item["order_no"]: item for item in body["suggestions"]}
            self.assertEqual(by_order[1]["judged_by"], "local")
            self.assertEqual(by_order[1]["verdict"], "correct")
            self.assertEqual(by_order[2]["judged_by"], "model")
            self.assertNotIn("paper_id", body)
            self.assertNotIn(BAIT_ID, done.text)
            self.assertEqual(app.state.loop.practice.confirmation_count(), 0)
            transcribe = json.dumps(captured_transcribe(model.transcribe_asks[0]), ensure_ascii=False)
            judged = json.dumps(captured_judge(model.judge_asks[0]), ensure_ascii=False)
            for hidden in (BAIT_ID, BAIT_NAME, STUDENT_ID, paper_id, "stem-choice-hidden", PIXELS.decode()):
                self.assertNotIn(hidden, transcribe)
                self.assertNotIn(hidden, judged)
            self.assertNotIn("stem-choice-hidden", judged)
            self.assertIn("stem-solution-hidden", judged)
            self.assertNotIn("standard_answer", transcribe)
            again = client.post(_start(intake_id), json={}, headers=_csrf(token))
            self.assertEqual(again.status_code, 202, again.text)
            admin = _login(client, ACTOR_ADMIN_ID)
            visible = client.get("/api/practice/ai-runs/" + run_id, headers=_csrf(admin))
            self.assertEqual(visible.status_code, 200, visible.text)

    def test_other_teacher_is_forbidden(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _copy_user(app, "teacher-other-r6", "teacher")
            opened = _ready(app, client, token)
            uploaded = _put(client, token, str(opened["paper_id"]))
            other = _login(client, "teacher-other-r6")
            refused = client.post(_start(uploaded.json()["intake_id"]), json={}, headers=_csrf(other))
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["code"], "permission_denied")

    def test_student_is_forbidden(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _copy_user(app, "student-login-r6", "student")
            opened = _ready(app, client, token)
            uploaded = _put(client, token, str(opened["paper_id"]))
            student = _login(client, "student-login-r6")
            refused = client.post(_start(uploaded.json()["intake_id"]), json={}, headers=_csrf(student))
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["code"], "permission_denied")

    def test_missing_csrf_is_rejected(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            opened = _ready(app, client, token)
            uploaded = _put(client, token, str(opened["paper_id"]))
            refused = client.post(_start(uploaded.json()["intake_id"]), json={})
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["code"], "csrf")

    def test_second_start_while_running_is_in_progress(self) -> None:
        app = _app()
        model = MockModel(scenario="hold")
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            opened = _ready(app, client, token)
            uploaded = _put(client, token, str(opened["paper_id"]))
            app.state.loop = replace(app.state.loop, model=model)
            try:
                started = client.post(_start(uploaded.json()["intake_id"]), json={}, headers=_csrf(token))
                self.assertEqual(started.status_code, 202, started.text)
                self.assertTrue(model.entered.wait(3))
                again = client.post(_start(uploaded.json()["intake_id"]), json={}, headers=_csrf(token))
            finally:
                model.hold.set()
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["code"], "ai_run_in_progress")

    def test_daily_limit_does_not_block_confirm(self) -> None:
        app = _app()
        with mock.patch.dict(os.environ, {"K12_AI_DAILY_LIMIT": "1"}):
            with TestClient(app) as client:
                token = _login(client, ACTOR_TEACHER_ID)
                opened = _ready(app, client, token)
                uploaded = _put(client, token, str(opened["paper_id"]))
                intake_id = uploaded.json()["intake_id"]
                started = client.post(_start(intake_id), json={}, headers=_csrf(token))
                self.assertEqual(started.status_code, 202, started.text)
                done = _wait(client, started.json()["run_id"])
                self.assertEqual(done.json()["status"], "succeeded")
                limited = client.post(_start(intake_id), json={}, headers=_csrf(token))
                saved = _confirm(client, token, opened)
                status = client.get("/api/practice/papers/" + str(opened["paper_id"]) + "/intake")
        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertEqual(limited.json()["code"], "ai_daily_limit")
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(status.json()["pages"][0]["received"])

    def test_model_failures_do_not_block_confirm(self) -> None:
        for scenario, code in (
            ("timeout", "timeout"),
            ("auth", "auth_failed"),
            ("invalid", "model_output_invalid"),
        ):
            with self.subTest(scenario=scenario):
                app = _app()
                model = MockModel(scenario=scenario)
                with TestClient(app) as client:
                    token = _login(client, ACTOR_TEACHER_ID)
                    opened = _ready(app, client, token)
                    uploaded = _put(client, token, str(opened["paper_id"]))
                    app.state.loop = replace(app.state.loop, model=model)
                    started = client.post(_start(uploaded.json()["intake_id"]), json={}, headers=_csrf(token))
                    self.assertEqual(started.status_code, 202, started.text)
                    done = _wait(client, started.json()["run_id"])
                    saved = _confirm(client, token, opened)
                    status = client.get("/api/practice/papers/" + str(opened["paper_id"]) + "/intake")
                self.assertEqual(done.json()["status"], "failed")
                self.assertEqual(done.json()["error_code"], code)
                self.assertEqual(done.json()["suggestions"], [])
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertTrue(status.json()["pages"][0]["received"])

    def test_log_audit_and_webhook_omit_secrets(self) -> None:
        server = _listen()
        app = _app()
        buffer = StringIO()
        model = MockModel(transcription=TRANSCRIPTION)
        try:
            with mock.patch.dict(os.environ, _quiet_proxy(_url(server))):
                with TestClient(app) as client:
                    token = _login(client, ACTOR_TEACHER_ID)
                    opened = _ready(app, client, token)
                    _items(app, str(opened["paper_id"]))
                    with redirect_stdout(buffer):
                        uploaded = _put(client, token, str(opened["paper_id"]))
                    self.assertEqual(uploaded.status_code, 200, uploaded.text)
                    app.state.loop = replace(app.state.loop, model=model)
                    with mock.patch.object(MemoryRuns, "finish", side_effect=RuntimeError("forced-store")):
                        with redirect_stdout(buffer):
                            started = client.post(
                                _start(uploaded.json()["intake_id"]),
                                json={},
                                headers=_csrf(token),
                            )
                            self.assertEqual(started.status_code, 202, started.text)
                            deadline = time.time() + 5
                            while time.time() < deadline and server.hits == 0:  # type: ignore[attr-defined]
                                time.sleep(0.02)
                            app.state.errors.wait()
            self.assertEqual(server.hits, 1)  # type: ignore[attr-defined]
            body = json.loads(server.received[0].decode("utf-8"))  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(set(body), {"time", "request_id", "module", "event", "outcome"})
        self.assertEqual(body["event"], "use_case_failed")
        leaked = (BAIT_ID, BAIT_NAME, STUDENT_ID, PIXELS.decode(), TRANSCRIPTION, PROMPT_MARK, PROBE)
        text = buffer.getvalue() + json.dumps(body) + _audit_text(app)
        for hidden in leaked:
            self.assertNotIn(hidden, text)


def _app() -> object:
    env = {
        "K12_LOG_FILE": "0",
        "K12_PAPER_QR": "on",
        "K12_PG_DSN": "",
        "K12_ENV": "development",
        "K12_AI_PROVIDER": "mock",
        "K12_AI_MOCK": "ok",
        "K12_AI_API_KEY": PROBE,
    }
    with mock.patch.dict(os.environ, env, clear=False):
        return create_app(seed=True)


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/login", json={"username": username, "secret": SYNTH_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.status_code)
    return str(response.json()["csrf_token"])


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


def _ready(app: object, client: TestClient, token: str) -> dict[str, object]:
    _plant(app)
    published = client.post("/api/catalog/q-v1/publish", headers=_csrf(token))
    if published.status_code != 200:
        raise AssertionError(published.status_code)
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
        raise AssertionError(opened.status_code)
    return opened.json()


def _items(app: object, paper_id: str) -> None:
    app.state.loop.items.set_items(  # type: ignore[attr-defined]
        paper_id,
        (
            PracticeItem(
                paper_id=paper_id,
                order_no=1,
                question_version_id="q-choice-r6",
                answer_version_id="a-choice-r6",
                stem_text="stem-choice-hidden",
                answer_text="A",
                option_text="A\nB",
                page_no=1,
                boxes=(ItemBox(1, 1, 10, 10, 40, 20, "letter"),),
            ),
            PracticeItem(
                paper_id=paper_id,
                order_no=2,
                question_version_id="q-solution-r6",
                answer_version_id="a-solution-r6",
                stem_text="stem-solution-hidden",
                answer_text="2",
                page_no=1,
                boxes=(ItemBox(1, 1, 10, 100, 80, 40, "large"),),
            ),
        ),
    )


def _put(client: TestClient, token: str, paper_id: str) -> object:
    return client.put(
        "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
        content=_jpeg(),
        headers={"Content-Type": "image/jpeg", "X-K12-CSRF": token},
    )


def _confirm(client: TestClient, token: str, opened: dict[str, object]) -> object:
    body = {
        "operation_key": "key-ai-" + str(opened["paper_id"]),
        "paper_id": opened["paper_id"],
        "sub_question_id": "sq-1",
        "teacher_id": ACTOR_TEACHER_ID,
        "review_version_id": "rev-1",
        "decision": "adopt",
        "fixture_answer_id": opened["fixture_answer_id"],
    }
    return client.post("/api/practice/confirmations", json=body, headers=_csrf(token))


def _start(intake_id: str) -> str:
    return "/api/practice/intake/" + intake_id + "/ai-runs"


def _wait(client: TestClient, run_id: str) -> object:
    deadline = time.time() + 5
    response = client.get("/api/practice/ai-runs/" + run_id)
    while time.time() < deadline:
        if response.status_code == 200 and response.json()["status"] in {"succeeded", "failed"}:
            return response
        time.sleep(0.02)
        response = client.get("/api/practice/ai-runs/" + run_id)
    return response


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


def _audit_text(app: object) -> str:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    parts: list[str] = []
    for row in book.rows:
        parts.append(" ".join((row.action, row.target_id, row.detail_json, row.outcome)))
    for event in book.events:
        parts.append(json.dumps(event.fields(), ensure_ascii=False))
    return "\n".join(parts)


def _jpeg() -> bytes:
    def segment(marker: int, payload: bytes) -> bytes:
        length = len(payload) + 2
        return bytes((0xFF, marker, (length >> 8) & 0xFF, length & 0xFF)) + payload

    return b"\xff\xd8" + segment(0xDA, b"") + PIXELS + b"\xff\xd9"


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


def _quiet_proxy(url: str) -> dict[str, str]:
    return {
        "K12_ERROR_WEBHOOK_URL": url,
        "NO_PROXY": "127.0.0.1",
        "no_proxy": "127.0.0.1",
        "K12_LOG_FILE": "0",
        "K12_AI_PROVIDER": "mock",
        "K12_AI_API_KEY": PROBE,
    }
