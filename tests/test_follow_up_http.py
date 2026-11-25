"""HTTP follow-up. The issuing teacher is the session, and AI text is not a decision."""

from __future__ import annotations

import json
import os
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from unittest import mock

from fastapi.testclient import TestClient

from backend.ai.domain.records import Run, Suggestion
from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.identity.domain.records import Grant, Student

STUDENT_ID = "student-hidden-r8"
EXTERNAL_ID = "synth-r8-ext"
NAME = "name-bait-r8"
STEM = "synth-r8-stem"


class FollowUpHttpTest(unittest.TestCase):
    def test_omitted_orders_ignore_an_unconfirmed_suggestion(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _issued(app, client, token, 3)
            _replace_stem(app)
            intake_id = _upload(client, token, paper_id)
            _seed(app, intake_id, paper_id, (_fact(paper_id, 1, "incorrect"),))
            saved = _decide(client, token, paper_id, 2, {"action": "manual", "verdict": "incorrect"})
            correct = _decide(client, token, paper_id, 3, {"action": "manual", "verdict": "correct"})
            source = _paper_row(app, paper_id)
            decisions = app.state.loop.decisions.history(paper_id)  # type: ignore[attr-defined]
            followed = client.post(_follow(paper_id), json={}, headers=_csrf(token))
            listed = client.get("/api/practice/papers")
            issued = client.post("/api/practice/papers", json=_issue_body(1), headers=_csrf(token))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(correct.status_code, 200, correct.text)
        self.assertEqual(followed.status_code, 200, followed.text)
        body = followed.json()
        self.assertNotEqual(body["paper_id"], paper_id)
        self.assertEqual(body["source_paper_id"], paper_id)
        self.assertEqual(body["student_id"], STUDENT_ID)
        self.assertNotIn(EXTERNAL_ID, followed.text)
        self.assertNotIn(NAME, followed.text)
        self.assertNotIn(STEM, followed.text)
        copied = app.state.loop.items.items_of(body["paper_id"])  # type: ignore[attr-defined]
        self.assertEqual(len(copied), 1)
        self.assertEqual(app.state.loop.practice.get_paper(paper_id), source)  # type: ignore[attr-defined]
        self.assertEqual(app.state.loop.decisions.history(paper_id), decisions)  # type: ignore[attr-defined]
        row = next(item for item in listed.json()["papers"] if item["paper_id"] == body["paper_id"])
        self.assertEqual(row["source_paper_id"], paper_id)
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertEqual(issued.json()["source_paper_id"], "")
        detail = _audit_details(app)[-1]
        self.assertEqual(set(detail), {"source_paper_id", "paper_id", "item_count"})
        blob = json.dumps(detail)
        for hidden in (STUDENT_ID, EXTERNAL_ID, NAME, STEM, "synth-a"):
            self.assertNotIn(hidden, blob)

    def test_explicit_orders_and_refuses(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _issued(app, client, token, 2)
            _decide(client, token, paper_id, 1, {"action": "manual", "verdict": "incorrect"})
            kept = client.post(_follow(paper_id), json={"order_nos": [1]}, headers=_csrf(token))
            duplicate = client.post(_follow(paper_id), json={"order_nos": [1, 1]}, headers=_csrf(token))
            missing = client.post(_follow(paper_id), json={"order_nos": [9]}, headers=_csrf(token))
            zero = client.post(_follow(paper_id), json={"order_nos": [0]}, headers=_csrf(token))
            unconfirmed = client.post(_follow(paper_id), json={"order_nos": [2]}, headers=_csrf(token))
        self.assertEqual(kept.status_code, 200, kept.text)
        self.assertEqual(len(app.state.loop.items.items_of(kept.json()["paper_id"])), 1)  # type: ignore[attr-defined]
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["code"], "invalid_order_no")
        self.assertEqual(missing.json()["code"], "invalid_order_no")
        self.assertEqual(zero.json()["code"], "invalid_order_no")
        self.assertEqual(unconfirmed.status_code, 409, unconfirmed.text)
        self.assertEqual(unconfirmed.json()["code"], "decision_required")

    def test_all_correct_or_ungraded_refuses(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            graded = _issued(app, client, token, 1)
            bare = _issued(app, client, token, 1)
            _decide(client, token, graded, 1, {"action": "manual", "verdict": "correct"})
            all_correct = client.post(_follow(graded), json={}, headers=_csrf(token))
            ungraded = client.post(_follow(bare), json={}, headers=_csrf(token))
        self.assertEqual(all_correct.status_code, 409, all_correct.text)
        self.assertEqual(all_correct.json()["code"], "no_retry_items")
        self.assertEqual(ungraded.json()["code"], "no_retry_items")

    def test_missing_other_teacher_and_revoked_grant(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _issued(app, client, token, 1)
            _decide(client, token, paper_id, 1, {"action": "manual", "verdict": "incorrect"})
            missing = client.post(_follow("paper-synth-r8-missing"), json={}, headers=_csrf(token))
            _copy_user(app, "teacher-synth-r8-other")
            other_token = _login(client, "teacher-synth-r8-other")
            other = client.post(_follow(paper_id), json={}, headers=_csrf(other_token))
            admin = _login(client, ACTOR_ADMIN_ID)
            admin_denied = client.post(_follow(paper_id), json={}, headers=_csrf(admin))
            token = _login(client, ACTOR_TEACHER_ID)
            _revoke(app)
            revoked = client.post(_follow(paper_id), json={}, headers=_csrf(token))
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["code"], "not_found")
        self.assertEqual(other.status_code, 403, other.text)
        self.assertEqual(other.json()["code"], "permission_denied")
        self.assertEqual(admin_denied.status_code, 403, admin_denied.text)
        self.assertEqual(revoked.status_code, 403, revoked.text)
        self.assertEqual(revoked.json()["code"], "permission_denied")

    def test_retired_question_writes_no_paper(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _issued(app, client, token, 1)
            _decide(client, token, paper_id, 1, {"action": "manual", "verdict": "incorrect"})
            current = app.state.loop.approvals.read_snapshot("q-v1")  # type: ignore[attr-defined]
            app.state.loop.approvals.put(replace(current, retired=True))  # type: ignore[attr-defined]
            before = app.state.loop.practice.paper_count()  # type: ignore[attr-defined]
            refused = client.post(_follow(paper_id), json={}, headers=_csrf(token))
            after = app.state.loop.practice.paper_count()  # type: ignore[attr-defined]
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["code"], "retired")
        self.assertEqual(before, after)

    def test_production_does_not_bind_an_attempt(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login(client, ACTOR_TEACHER_ID)
            paper_id = _issued(app, client, token, 1)
            _decide(client, token, paper_id, 1, {"action": "manual", "verdict": "blank"})
            with mock.patch.dict(os.environ, {"K12_ENV": "production"}):
                followed = client.post(_follow(paper_id), json={}, headers=_csrf(token))
        self.assertEqual(followed.status_code, 200, followed.text)
        self.assertEqual(followed.json()["fixture_answer_id"], "")
        self.assertIsNone(app.state.loop.practice.find_answer_for_paper(followed.json()["paper_id"]))  # type: ignore[attr-defined]


def _app() -> object:
    env = {"K12_LOG_FILE": "0", "K12_PG_DSN": "", "K12_ENV": "development", "K12_AI_PROVIDER": "mock"}
    with mock.patch.dict(os.environ, env, clear=False):
        return create_app(seed=True)


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/login", json={"username": username, "secret": SYNTH_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.text)
    return str(response.json()["csrf_token"])


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


def _issued(app: object, client: TestClient, token: str, count: int) -> str:
    _plant(app)
    published = client.post("/api/catalog/q-v1/publish", headers=_csrf(token))
    if published.status_code != 200:
        raise AssertionError(published.text)
    opened = client.post("/api/practice/papers", json=_issue_body(count), headers=_csrf(token))
    if opened.status_code != 200:
        raise AssertionError(opened.text)
    return str(opened.json()["paper_id"])


def _issue_body(count: int) -> dict[str, object]:
    body: dict[str, object] = {
        "student_id": STUDENT_ID,
        "subject_id": "math",
        "question_version_id": "q-v1",
        "review_version_id": "rev-1",
    }
    if count >= 2:
        body["items"] = [{"question_version_id": "q-v1"} for _ in range(count)]
    return body


def _replace_stem(app: object) -> None:
    current = app.state.loop.approvals.read_snapshot("q-v1")  # type: ignore[attr-defined]
    app.state.loop.approvals.put(replace(current, stem=STEM, answer_text="synth-a"))  # type: ignore[attr-defined]
    paper_ids = [row.paper_id for row in app.state.loop.practice.list_papers()]  # type: ignore[attr-defined]
    for paper_id in paper_ids:
        rows = app.state.loop.items.items_of(paper_id)  # type: ignore[attr-defined]
        if not rows:
            continue
        app.state.loop.items.set_items(  # type: ignore[attr-defined]
            paper_id,
            tuple(replace(row, stem_text=STEM, answer_text="synth-a") for row in rows),
        )


def _upload(client: TestClient, token: str, paper_id: str) -> str:
    uploaded = client.put(
        "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
        content=b"\xff\xd8" + b"IMAGE-BYTES-R8" + b"\xff\xd9",
        headers={"Content-Type": "image/jpeg", "X-K12-CSRF": token},
    )
    if uploaded.status_code != 200:
        raise AssertionError(uploaded.text)
    return str(uploaded.json()["intake_id"])


def _seed(app: object, intake_id: str, paper_id: str, facts: tuple[Suggestion, ...]) -> None:
    app.state.loop.ai_runs.insert(  # type: ignore[attr-defined]
        Run(
            run_id="run-synth-r8",
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


def _fact(paper_id: str, order_no: int, verdict: str) -> Suggestion:
    return Suggestion(
        run_id="run-synth-r8",
        paper_id=paper_id,
        order_no=order_no,
        transcription="synth-transcript",
        unreadable=False,
        confidence=0.91,
        verdict=verdict,
        reason="synth-reason",
        judged_by="model",
    )


def _decide(client: TestClient, token: str, paper_id: str, order_no: int, body: dict[str, str]) -> object:
    return client.put(
        "/api/practice/papers/" + paper_id + "/items/" + str(order_no) + "/decision",
        json=body,
        headers=_csrf(token),
    )


def _follow(paper_id: str) -> str:
    return "/api/practice/papers/" + paper_id + "/follow-up"


def _paper_row(app: object, paper_id: str) -> object:
    return app.state.loop.practice.get_paper(paper_id)  # type: ignore[attr-defined]


def _plant(app: object) -> None:
    identity = app.state.loop.identity  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    if identity.students.by_id(STUDENT_ID) is None:
        identity.students.insert(
            Student(
                student_id=STUDENT_ID,
                external_id=EXTERNAL_ID,
                name=NAME,
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


def _revoke(app: object) -> None:
    identity = app.state.loop.identity  # type: ignore[attr-defined]
    grant = identity.grants.active(ACTOR_TEACHER_ID, STUDENT_ID, "math")
    if grant is None:
        raise AssertionError("grant missing")
    identity.grants.revoke(grant.grant_id, datetime.now(timezone.utc))


def _copy_user(app: object, username: str) -> None:
    users = app.state.loop.identity.users  # type: ignore[attr-defined]
    teacher = users.by_username(ACTOR_TEACHER_ID)
    users.insert(replace(teacher, user_id=username, username=username, role="teacher"))


def _audit_details(app: object) -> list[dict[str, object]]:
    book = app.state.loop.identity.audits  # type: ignore[attr-defined]
    found: list[dict[str, object]] = []
    for row in book.rows:
        if row.action == "follow_up_paper_issued" and row.detail_json:
            found.append(json.loads(row.detail_json))
    return found
