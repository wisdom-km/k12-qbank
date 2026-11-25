"""Teacher conclusions over HTTP. The mock never calls a model."""

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

from backend.ai.domain.records import Run, Suggestion
from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.catalog.api import ApprovalSnapshot
from backend.identity.domain.records import Grant, Student
from backend.practice.adapters.memory_decision import MemoryDecisions
from backend.practice.domain.item import PracticeItem

STUDENT_ID = "student-hidden-r7"
TRANSCRIPT = "transcript-bait-r7"
COMMENT = "comment-bait-r7"
PROBE = "probe-key"


class DecisionHttpTest(unittest.TestCase):
    def test_adopt_revise_and_manual(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _paper(app, client, token)
            _items(app, paper_id)
            _type(app, "solution")
            intake_id = _upload(client, token, paper_id)
            _seed(
                app,
                intake_id,
                paper_id,
                (
                    _fact(paper_id, 1, "correct", 0.91, "local"),
                    _fact(paper_id, 2, "incorrect", 0.4, "model"),
                ),
            )
            review = client.get(_review(paper_id))
            self.assertEqual(review.status_code, 200, review.text)
            body = review.json()
            self.assertNotIn("student_id", review.text)
            self.assertNotIn(STUDENT_ID, review.text)
            by_order = {item["order_no"]: item for item in body["items"]}
            self.assertEqual(by_order[1]["question_type"], "solution")
            self.assertEqual(by_order[1]["suggestion"]["judged_by"], "local")
            self.assertEqual(by_order[2]["suggestion"]["needs_review"], True)
            self.assertIsNone(by_order[3]["suggestion"])
            self.assertEqual(by_order[3]["intake_status"], "received")
            adopted = _decide(client, token, paper_id, 1, {"action": "adopt"})
            revised = _decide(
                client,
                token,
                paper_id,
                2,
                {"action": "revise", "verdict": "partial", "comment": "步骤对了一半"},
            )
            manual = _decide(client, token, paper_id, 3, {"action": "manual", "verdict": "blank"})
        self.assertEqual(adopted.status_code, 200, adopted.text)
        self.assertEqual(adopted.json()["source"], "adopted")
        self.assertEqual(adopted.json()["verdict"], "correct")
        self.assertTrue(adopted.json()["agrees"])
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["source"], "revised")
        self.assertEqual(revised.json()["verdict"], "partial")
        self.assertEqual(revised.json()["ai_verdict"], "incorrect")
        self.assertEqual(manual.status_code, 200, manual.text)
        self.assertEqual(manual.json()["source"], "manual")
        self.assertEqual(manual.json()["verdict"], "blank")
        self.assertFalse(manual.json()["agrees"])

    def test_adopt_unsure_is_refused(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _paper(app, client, token)
            intake_id = _upload(client, token, paper_id)
            _seed(app, intake_id, paper_id, (_fact(paper_id, 1, "unsure", 0.2, "local", unreadable=True),))
            refused = _decide(client, token, paper_id, 1, {"action": "adopt"})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["code"], "cannot_adopt_unsure")

    def test_missing_suggestion_allows_only_manual(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _paper(app, client, token)
            refused = _decide(client, token, paper_id, 1, {"action": "adopt"})
            revised = _decide(client, token, paper_id, 1, {"action": "revise", "verdict": "incorrect"})
            saved = _decide(client, token, paper_id, 1, {"action": "manual", "verdict": "incorrect"})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["code"], "suggestion_required")
        self.assertEqual(revised.json()["code"], "suggestion_required")
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["source"], "manual")

    def test_revise_voids_the_previous_row(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _paper(app, client, token)
            intake_id = _upload(client, token, paper_id)
            _seed(app, intake_id, paper_id, (_fact(paper_id, 1, "correct", 0.91, "model"),))
            first = _decide(client, token, paper_id, 1, {"action": "adopt"})
            second = _decide(client, token, paper_id, 1, {"action": "revise", "verdict": "incorrect"})
            review = client.get(_review(paper_id))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        history = app.state.loop.decisions.history(paper_id)  # type: ignore[attr-defined]
        self.assertEqual(len(history), 2)
        by_source = {row.source: row for row in history}
        self.assertEqual(set(by_source), {"adopted", "revised"})
        self.assertTrue(by_source["adopted"].voided_at)
        self.assertEqual(by_source["revised"].verdict, "incorrect")
        self.assertEqual(by_source["revised"].voided_at, "")
        self.assertEqual(len(app.state.loop.decisions.currents(paper_id)), 1)  # type: ignore[attr-defined]
        self.assertEqual(review.json()["items"][0]["decision"]["verdict"], "incorrect")
        self.assertEqual(review.json()["confirmed"], 1)

    def test_replaced_photo_is_suggestion_stale(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _paper(app, client, token)
            intake_id = _upload(client, token, paper_id)
            _seed(app, intake_id, paper_id, (_fact(paper_id, 1, "correct", 0.91, "model"),))
            replaced = client.put(
                "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual&replace=true",
                content=_jpeg(),
                headers={"Content-Type": "image/jpeg", "X-K12-CSRF": token},
            )
            refused = _decide(client, token, paper_id, 1, {"action": "adopt"})
            saved = _decide(client, token, paper_id, 1, {"action": "manual", "verdict": "blank"})
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertNotEqual(replaced.json()["intake_id"], intake_id)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["code"], "suggestion_stale")
        self.assertEqual(saved.status_code, 200, saved.text)

    def test_adopt_confident_keeps_local_rows_at_the_threshold(self) -> None:
        app = _app()
        with mock.patch.dict(os.environ, {"K12_AI_REVIEW_THRESHOLD": "0.6"}):
            with TestClient(app) as client:
                token = _login(client, ACTOR_TEACHER_ID)
                paper_id = _paper(app, client, token)
                _items(
                    app,
                    paper_id,
                    (
                        _item(paper_id, 1),
                        _item(paper_id, 2),
                        _item(paper_id, 3),
                        _item(paper_id, 4),
                        _item(paper_id, 5),
                    ),
                )
                intake_id = _upload(client, token, paper_id)
                _seed(
                    app,
                    intake_id,
                    paper_id,
                    (
                        _fact(paper_id, 1, "correct", 0.6, "local"),
                        _fact(paper_id, 2, "correct", 0.59, "local"),
                        _fact(paper_id, 3, "correct", 0.99, "model"),
                        _fact(paper_id, 4, "unsure", 0.95, "local"),
                        _fact(paper_id, 5, "incorrect", 0.91, "local"),
                    ),
                )
                held = _decide(client, token, paper_id, 5, {"action": "adopt"})
                taken = client.post(_bulk(paper_id), json={}, headers=_csrf(token))
                review = client.get(_review(paper_id))
        self.assertEqual(held.status_code, 200, held.text)
        self.assertEqual(taken.status_code, 200, taken.text)
        self.assertEqual(taken.json()["threshold"], 0.6)
        self.assertEqual(taken.json()["order_nos"], [1])
        decided = {
            item["order_no"]: item["decision"]["source"]
            for item in review.json()["items"]
            if item["decision"] is not None
        }
        self.assertEqual(decided, {1: "adopted", 5: "adopted"})

    def test_threshold_comes_from_the_environment(self) -> None:
        app = _app()
        with mock.patch.dict(os.environ, {"K12_AI_REVIEW_THRESHOLD": "0.95"}):
            with TestClient(app) as client:
                token = _login(client, ACTOR_TEACHER_ID)
                paper_id = _paper(app, client, token)
                _items(app, paper_id, (_item(paper_id, 1), _item(paper_id, 2)))
                intake_id = _upload(client, token, paper_id)
                _seed(
                    app,
                    intake_id,
                    paper_id,
                    (
                        _fact(paper_id, 1, "correct", 0.95, "local"),
                        _fact(paper_id, 2, "correct", 0.94, "local"),
                    ),
                )
                review = client.get(_review(paper_id))
                taken = client.post(_bulk(paper_id), json={}, headers=_csrf(token))
        self.assertEqual(review.json()["threshold"], 0.95)
        self.assertEqual(review.json()["items"][0]["suggestion"]["needs_review"], False)
        self.assertEqual(review.json()["items"][1]["suggestion"]["needs_review"], True)
        self.assertEqual(taken.json()["order_nos"], [1])

    def test_adopted_agrees_and_revised_keeps_the_ai_verdict(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _paper(app, client, token)
            _items(app, paper_id, (_item(paper_id, 1), _item(paper_id, 2)))
            intake_id = _upload(client, token, paper_id)
            _seed(
                app,
                intake_id,
                paper_id,
                (
                    _fact(paper_id, 1, "correct", 0.91, "model"),
                    _fact(paper_id, 2, "partial", 0.42, "model"),
                ),
            )
            _decide(client, token, paper_id, 1, {"action": "adopt"})
            _decide(client, token, paper_id, 2, {"action": "revise", "verdict": "incorrect"})
        details = _details(app)
        self.assertEqual(len(details), 2)
        self.assertEqual(set(details[0]), {"paper_id", "order_no", "action", "verdict", "agrees"})
        self.assertEqual(details[0]["action"], "adopt")
        self.assertEqual(details[0]["verdict"], "correct")
        self.assertIs(details[0]["agrees"], True)
        self.assertEqual(details[1]["action"], "revise")
        self.assertEqual(details[1]["verdict"], "incorrect")
        self.assertIs(details[1]["agrees"], False)
        kept = app.state.loop.decisions.current(paper_id, 2)  # type: ignore[attr-defined]
        self.assertEqual(kept.ai_verdict, "partial")
        self.assertEqual(kept.ai_confidence, 0.42)
        self.assertTrue(kept.ai_run_id)

    def test_other_teacher_student_and_missing_csrf_are_refused(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _copy_user(app, "teacher-other-r7", "teacher")
            _copy_user(app, "student-login-r7", "student")
            paper_id = _paper(app, client, token)
            other = _login(client, "teacher-other-r7")
            forbidden = _decide(client, other, paper_id, 1, {"action": "manual", "verdict": "blank"})
            student = _login(client, "student-login-r7")
            student_call = _decide(client, student, paper_id, 1, {"action": "manual", "verdict": "blank"})
            _login(client, ACTOR_TEACHER_ID)
            missing = client.put(_decision(paper_id, 1), json={"action": "manual", "verdict": "blank"})
        self.assertEqual(forbidden.status_code, 403, forbidden.text)
        self.assertEqual(forbidden.json()["code"], "permission_denied")
        self.assertEqual(student_call.status_code, 403, student_call.text)
        self.assertEqual(student_call.json()["code"], "permission_denied")
        self.assertEqual(missing.status_code, 403, missing.text)
        self.assertEqual(missing.json()["code"], "csrf")

    def test_production_retires_confirmations_and_skips_synthetic_attempt(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            _plant(app)
            published = client.post("/api/catalog/q-v1/publish", headers=_csrf(token))
            self.assertEqual(published.status_code, 200, published.text)
            with mock.patch.dict(os.environ, {"K12_ENV": "production"}):
                with mock.patch("backend.bootstrap.routes_practice.synthetic_attempt_text") as stub:
                    opened = client.post("/api/practice/papers", json=_issue_body(), headers=_csrf(token))
                    multi = client.post(
                        "/api/practice/papers",
                        json={
                            **_issue_body(),
                            "items": [{"question_version_id": "q-v1"}, {"question_version_id": "q-v1"}],
                        },
                        headers=_csrf(token),
                    )
                    retired = client.post(
                        "/api/practice/confirmations",
                        json={
                            "operation_key": "key-r7-retired",
                            "paper_id": "paper-missing-r7",
                            "sub_question_id": "sq-1",
                            "review_version_id": "rev-1",
                            "decision": "adopt",
                            "fixture_answer_id": "fixture-answer-r7",
                        },
                        headers=_csrf(token),
                    )
                    calls = stub.call_count
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()["fixture_answer_id"], "")
        self.assertEqual(multi.status_code, 200, multi.text)
        self.assertEqual(multi.json()["fixture_answer_id"], "")
        self.assertEqual(retired.status_code, 410, retired.text)
        self.assertEqual(retired.json()["code"], "confirmations_retired")
        self.assertIn("/decision", retired.json()["message"])
        self.assertNotIn(STUDENT_ID, retired.text)
        self.assertEqual(calls, 0)
        self.assertEqual(app.state.loop.practice.confirmation_count(), 0)  # type: ignore[attr-defined]

    def test_audit_log_and_webhook_omit_the_transcript(self) -> None:
        server = _listen()
        app = _app()
        buffer = StringIO()
        try:
            with mock.patch.dict(os.environ, {"K12_ERROR_WEBHOOK_URL": _url(server), "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
                with TestClient(app) as client:
                    token = _login(client, ACTOR_TEACHER_ID)
                    paper_id = _paper(app, client, token)
                    intake_id = _upload(client, token, paper_id)
                    _seed(
                        app,
                        intake_id,
                        paper_id,
                        (_fact(paper_id, 1, "correct", 0.91, "model", transcription=TRANSCRIPT),),
                    )
                    with redirect_stdout(buffer):
                        saved = _decide(
                            client,
                            token,
                            paper_id,
                            1,
                            {
                                "action": "revise",
                                "verdict": "incorrect",
                                "corrected_transcription": TRANSCRIPT,
                                "comment": COMMENT,
                            },
                        )
                    self.assertEqual(saved.status_code, 200, saved.text)
                    with mock.patch.object(MemoryDecisions, "replace", side_effect=RuntimeError("forced-store")):
                        with redirect_stdout(buffer):
                            failed = _decide(
                                client,
                                token,
                                paper_id,
                                1,
                                {
                                    "action": "revise",
                                    "verdict": "partial",
                                    "corrected_transcription": TRANSCRIPT,
                                    "comment": COMMENT,
                                },
                            )
                            self.assertEqual(failed.status_code, 409, failed.text)
                            self.assertEqual(failed.json()["code"], "store_failed")
                            deadline = time.time() + 5
                            while time.time() < deadline and server.hits == 0:  # type: ignore[attr-defined]
                                time.sleep(0.02)
                            app.state.errors.wait()
            self.assertEqual(server.hits, 1)  # type: ignore[attr-defined]
            posted = json.loads(server.received[0].decode("utf-8"))  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(set(posted), {"time", "request_id", "module", "event", "outcome"})
        text = buffer.getvalue() + json.dumps(posted) + _audit_text(app)
        for hidden in (STUDENT_ID, TRANSCRIPT, COMMENT, PROBE):
            self.assertNotIn(hidden, text)
        self.assertIn("teacher_decision_saved", _audit_text(app))


def _app() -> object:
    env = {
        "K12_LOG_FILE": "0",
        "K12_PAPER_QR": "on",
        "K12_PG_DSN": "",
        "K12_ENV": "development",
        "K12_AI_PROVIDER": "mock",
        "K12_AI_MOCK": "ok",
        "K12_AI_API_KEY": PROBE,
        "K12_AI_REVIEW_THRESHOLD": "",
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


def _paper(app: object, client: TestClient, token: str) -> str:
    _plant(app)
    published = client.post("/api/catalog/q-v1/publish", headers=_csrf(token))
    if published.status_code != 200:
        raise AssertionError(published.text)
    opened = client.post("/api/practice/papers", json=_issue_body(), headers=_csrf(token))
    if opened.status_code != 200:
        raise AssertionError(opened.text)
    return str(opened.json()["paper_id"])


def _issue_body() -> dict[str, str]:
    return {
        "student_id": STUDENT_ID,
        "subject_id": "math",
        "question_version_id": "q-v1",
        "review_version_id": "rev-1",
    }


def _items(app: object, paper_id: str, rows: tuple[PracticeItem, ...] | None = None) -> None:
    app.state.loop.items.set_items(paper_id, rows or (_item(paper_id, 1), _item(paper_id, 2), _item(paper_id, 3)))  # type: ignore[attr-defined]


def _item(paper_id: str, order_no: int) -> PracticeItem:
    return PracticeItem(
        paper_id=paper_id,
        order_no=order_no,
        question_version_id="q-v1",
        answer_version_id="a-v1",
        stem_text="计算：(-3)+5",
        answer_text="2",
        page_no=1,
    )


def _type(app: object, kind: str) -> None:
    current = app.state.loop.approvals.read_snapshot("q-v1")  # type: ignore[attr-defined]
    app.state.loop.approvals.put(replace(current, type=kind))  # type: ignore[attr-defined]


def _upload(client: TestClient, token: str, paper_id: str) -> str:
    uploaded = client.put(
        "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
        content=_jpeg(),
        headers={"Content-Type": "image/jpeg", "X-K12-CSRF": token},
    )
    if uploaded.status_code != 200:
        raise AssertionError(uploaded.text)
    return str(uploaded.json()["intake_id"])


def _seed(
    app: object,
    intake_id: str,
    paper_id: str,
    facts: tuple[Suggestion, ...],
    *,
    run_id: str = "run-r7",
) -> None:
    app.state.loop.ai_runs.insert(  # type: ignore[attr-defined]
        Run(
            run_id=run_id,
            intake_id=intake_id,
            provider="mock",
            model="mock",
            prompt_version="transcribe-v1/judge-v1",
            status="succeeded",
            started_at="2026-11-25T00:00:00Z",
            finished_at="2026-11-25T00:00:01Z",
            external_match="unread",
            page_match="unread",
            suggestions=facts,
        )
    )


def _fact(
    paper_id: str,
    order_no: int,
    verdict: str,
    confidence: float,
    judged_by: str,
    *,
    unreadable: bool = False,
    transcription: str = "2",
    run_id: str = "run-r7",
) -> Suggestion:
    return Suggestion(
        run_id=run_id,
        paper_id=paper_id,
        order_no=order_no,
        transcription=transcription,
        unreadable=unreadable,
        confidence=confidence,
        verdict=verdict,
        reason="看不清" if unreadable else "与标准答案一致",
        judged_by=judged_by,
    )


def _decide(client: TestClient, token: str, paper_id: str, order_no: int, body: dict[str, str]) -> object:
    return client.put(_decision(paper_id, order_no), json=body, headers=_csrf(token))


def _decision(paper_id: str, order_no: int) -> str:
    return "/api/practice/papers/" + paper_id + "/items/" + str(order_no) + "/decision"


def _review(paper_id: str) -> str:
    return "/api/practice/papers/" + paper_id + "/review"


def _bulk(paper_id: str) -> str:
    return "/api/practice/papers/" + paper_id + "/decisions/adopt-confident"


def _details(app: object) -> list[dict[str, object]]:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    found: list[dict[str, object]] = []
    for row in book.rows:
        if row.action == "teacher_decision_saved" and row.detail_json:
            found.append(json.loads(row.detail_json))
    return found


def _audit_text(app: object) -> str:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    parts: list[str] = []
    for row in book.rows:
        parts.append(" ".join((row.action, row.target_id, row.detail_json, row.outcome)))
    for event in book.events:
        parts.append(json.dumps(event.fields(), ensure_ascii=False))
    return "\n".join(parts)


def _plant(app: object) -> None:
    identity = app.state.loop.identity  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    if identity.students.by_id(STUDENT_ID) is None:
        identity.students.insert(
            Student(
                student_id=STUDENT_ID,
                external_id="synth-r7-ext",
                name="name-bait-r7",
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


def _jpeg() -> bytes:
    return b"\xff\xd8" + b"IMAGE-BYTES-R7" + b"\xff\xd9"


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
