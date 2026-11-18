"""Review regressions for the synthetic M1 loop. No real student and no database."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.bootstrap.compose import Loop, compose
from http_client import signed_client
from backend.bootstrap.seed import load_fixture
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.publish_version import publish_version, revise_text
from backend.kernel.result import Err, Ok
from backend.practice.adapters.memory import MemoryPractice
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.api import IssuePaperCommand
from backend.practice.application.issue_paper import issue_paper
from backend.practice.application.render_paper import render_paper
from backend.practice.domain.confirm import Confirmation, OperationKey, PendingAnswer
from backend.practice.domain.page_face import PaperPage
from backend.practice.domain.paper import Paper, freeze_paper


ROOT = Path(__file__).resolve().parents[1]
ISSUE = {
    "teacher_id": "teacher-synth",
    "student_id": "student-synth",
    "subject_id": "math",
    "question_version_id": "q-v1",
    "review_version_id": "rev-1",
}


class BindOnce(MemoryPractice):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def place_issued(self, paper: object, answer: object) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("bind failed once")
        super().place_issued(paper, answer)  # type: ignore[arg-type]


class ReviewLoopTest(unittest.TestCase):
    def test_same_student_papers_keep_distinct_pages_and_omit_the_answer(self) -> None:
        with self._client() as client:
            self._publish(client)
            first = self._issue(client, "student-synth")
            second = self._issue(client, "student-synth")
            self.assertNotEqual(first["paper_id"], second["paper_id"])
            self.assertNotEqual(first["file_checksum"], second["file_checksum"])
            one = self._pdf(client, str(first["file_id"]))
            two = self._pdf(client, str(second["file_id"]))
        self.assertNotEqual(one, two)
        self.assertNotIn(str(second["paper_id"]).encode(), one)
        self.assertNotIn(str(first["paper_id"]).encode(), two)
        for pdf, row in ((one, first), (two, second)):
            self.assertIn(b"formula \\(-3\\)+5", pdf)
            self.assertIn(b"student student-synth", pdf)
            self.assertIn(b"name-rule omit", pdf)
            self.assertIn(b"page 1", pdf)
            self.assertIn(b"pages 1", pdf)
            self.assertIn(("paper " + str(row["paper_id"])).encode(), pdf)
            self.assertNotIn(b"answer ", pdf)

    def test_times_sign_renders_and_unsupported_text_stays_waiting(self) -> None:
        page = _page("2\u00d73")
        drawn = StdPdf().render(page)
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        self.assertIn(b"/Encoding /WinAnsiEncoding", drawn)
        self.assertIn("formula 2\u00d73".encode("cp1252"), drawn)
        self.assertNotIn(b"answer ", drawn)
        refused = StdPdf().render(_page("\u221a2"))
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertEqual(refused.code, "not_rendered")
        self.assertEqual(refused.message, "this synthetic page cannot encode the formula")
        with self._client() as client:
            self._publish(client)
            edited = client.post(
                "/api/catalog/q-v1/revise",
                json={"stem": "\u8ba1\u7b97\uff1a\u221a2", "answer_text": "\u5f85\u5b9a"},
            )
            self.assertEqual(edited.status_code, 200)
            new_id = edited.json()["question_version_id"]
            self.assertEqual(new_id, "q-v2")
            self.assertEqual(edited.json()["question_approved"], False)
            early = client.post("/api/practice/papers", json=dict(ISSUE, question_version_id=new_id))
            self.assertEqual(early.status_code, 409)
            self.assertEqual(early.json()["code"], "not_approved")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)
            published = client.post("/api/catalog/" + new_id + "/publish")
            self.assertEqual(published.status_code, 200)
            opened = client.post("/api/practice/papers", json=dict(ISSUE, question_version_id=new_id))
            self.assertEqual(opened.status_code, 200, opened.text)
            body = opened.json()
            self.assertEqual(body["status"], "\u5f85\u6e32\u67d3")
            self.assertIsNone(body["file_id"])
            self.assertEqual(body["render_code"], "not_rendered")
            self.assertEqual(body["render_message"], "this synthetic page cannot encode the formula")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 1)
            attempt = client.get("/api/practice/papers/" + body["paper_id"] + "/attempt")
            self.assertEqual(attempt.status_code, 200)
            self.assertEqual(attempt.json()["answer_text"], "\u5b66\u751f\u5199\u4e0b\u4e86 5")
            self.assertNotEqual(attempt.json()["answer_text"], "\u5f85\u5b9a")

    def test_waiting_paper_keeps_the_frozen_formula_after_a_bank_edit(self) -> None:
        loop = compose()
        load_fixture(loop)
        published = publish_version("q-v1", loop.approvals, loop.logger, "req-pub")
        self.assertIsInstance(published, Ok)
        issued = issue_paper(
            _command("q-v1"),
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.logger,
            "req-issue",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(issued, Ok)
        assert isinstance(issued, Ok)
        self.assertEqual(issued.value.status, "\u5f85\u6e32\u67d3")
        self.assertEqual(issued.value.formula, "(-3)+5")
        same = revise_text("q-v1", "\u8ba1\u7b97\uff1a(-3)+5", "2", loop.approvals, loop.logger, "req-same")
        self.assertIsInstance(same, Ok)
        assert isinstance(same, Ok)
        self.assertEqual(same.value.question_version_id, "q-v1")
        revised = revise_text("q-v1", "\u8ba1\u7b97\uff1a2\u00d73", "6", loop.approvals, loop.logger, "req-rev")
        self.assertIsInstance(revised, Ok)
        assert isinstance(revised, Ok)
        self.assertEqual(revised.value.question_version_id, "q-v2")
        self.assertEqual(revised.value.answer_version_id, "a-v2")
        self.assertFalse(revised.value.question_approved)
        original = loop.approvals.read_snapshot("q-v1")
        assert original is not None
        self.assertEqual(original.stem, "\u8ba1\u7b97\uff1a(-3)+5")
        self.assertEqual(original.answer_text, "2")
        self.assertTrue(original.question_approved)
        self.assertTrue(original.answer_approved)
        live = loop.approvals.read_snapshot("q-v1")
        assert live is not None
        loop.approvals.put(replace(live, stem="\u8ba1\u7b97\uff1a9+9", answer_text="18"))
        drawn = render_paper(
            issued.value.paper_id,
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.files,
            loop.renderer,
            loop.logger,
            "req-render",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(drawn, Ok)
        assert isinstance(drawn, Ok)
        self.assertEqual(drawn.value.question_version_id, "q-v1")
        old_pdf = loop.files.read(drawn.value.file_id or "")
        assert old_pdf is not None
        self.assertIn(b"\\(-3\\)+5", old_pdf)
        self.assertNotIn(b"9+9", old_pdf)
        self.assertNotIn("2\u00d73".encode("latin-1"), old_pdf)
        self.assertNotIn(b"answer ", old_pdf)
        checksum = drawn.value.file_checksum
        self.assertEqual(hashlib.sha256(old_pdf).hexdigest(), checksum)
        blocked = issue_paper(
            _command("q-v2"),
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.logger,
            "req-block",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(blocked, Err)
        assert isinstance(blocked, Err)
        self.assertEqual(blocked.code, "not_approved")
        self.assertEqual(loop.practice.paper_count(), 1)
        again = publish_version("q-v2", loop.approvals, loop.logger, "req-pub-2")
        self.assertIsInstance(again, Ok)
        newer = issue_paper(
            _command("q-v2"),
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.logger,
            "req-new",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(newer, Ok)
        assert isinstance(newer, Ok)
        rendered_new = render_paper(
            newer.value.paper_id,
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.files,
            loop.renderer,
            loop.logger,
            "req-render-2",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(rendered_new, Ok)
        assert isinstance(rendered_new, Ok)
        new_pdf = loop.files.read(rendered_new.value.file_id or "")
        assert new_pdf is not None
        self.assertIn("2\u00d73".encode("latin-1"), new_pdf)
        self.assertNotIn(b"\\(-3\\)+5", new_pdf)
        self.assertNotIn(b"answer ", new_pdf)
        kept = loop.files.read(drawn.value.file_id or "")
        self.assertEqual(kept, old_pdf)
        self.assertEqual(hashlib.sha256(kept or b"").hexdigest(), checksum)
        second_edit = revise_text(
            "q-v1",
            "\u8ba1\u7b97\uff1a(-9)+9",
            "0",
            loop.approvals,
            loop.logger,
            "req-rev-2",
        )
        self.assertIsInstance(second_edit, Ok)
        assert isinstance(second_edit, Ok)
        self.assertEqual(second_edit.value.question_version_id, "q-v3")
        self.assertIsNotNone(loop.approvals.read_snapshot("q-v1"))
        self.assertIsNotNone(loop.approvals.read_snapshot("q-v2"))

    def test_missing_item_order_writes_nothing(self) -> None:
        with self._client() as client:
            self._publish(client)
            snap = client.app.state.loop.approvals.read_snapshot("q-v1")
            assert snap is not None
            client.app.state.loop.approvals.put(replace(snap, item_order=()))
            refused = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(refused.status_code, 409)
            self.assertEqual(refused.json()["code"], "not_frozen")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)
            self.assertEqual(client.app.state.loop.practice.paper_count(), 0)
            self.assertIsNone(client.app.state.loop.practice.find_answer_for_paper("missing"))

    def test_bind_failure_leaves_no_orphan_and_retry_binds_one_answer(self) -> None:
        practice = BindOnce()
        with self._client(self._loop(practice=practice)) as client:
            self._publish(client)
            failed = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(failed.status_code, 409)
            self.assertEqual(failed.json()["code"], "store_failed")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)
            self.assertEqual(practice.paper_count(), 0)
            opened = self._issue(client, "student-synth")
            self.assertEqual(opened["status"], "\u53ef\u6253\u5370")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 1)
            self.assertEqual(practice.paper_count(), 1)
            attempt = client.get("/api/practice/papers/" + str(opened["paper_id"]) + "/attempt")
            self.assertEqual(attempt.status_code, 200)
            self.assertEqual(attempt.json()["paper_id"], opened["paper_id"])
            self.assertEqual(attempt.json()["answer_text"], "\u5b66\u751f\u5199\u4e0b\u4e86 5")
            self.assertNotEqual(attempt.json()["answer_text"], "2")
            self.assertEqual(attempt.json()["fixture_answer_id"], opened["fixture_answer_id"])

    def test_list_and_count_hide_records_the_teacher_cannot_see(self) -> None:
        with self._client() as client:
            self._publish(client)
            store = client.app.state.loop.practice
            hidden = _stored_paper("paper-hidden", "teacher-b", "student-other")
            stranger = _stored_paper("paper-stranger", "teacher-synth", "student-other")
            store.add_paper(hidden)
            store.add_paper(stranger)
            _confirm(store, hidden, "conf-hidden", "key-hidden", "teacher-b")
            _confirm(store, stranger, "conf-stranger", "key-stranger", "teacher-synth")
            self.assertEqual(store.confirmation_count(), 2)
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)
            self.assertEqual(client.get("/api/practice/confirmations/count").json()["count"], 0)
            opened = self._issue(client, "student-synth")
            body = {
                "operation_key": "key-web-visible",
                "paper_id": opened["paper_id"],
                "sub_question_id": "sq-1",
                "teacher_id": "teacher-synth",
                "review_version_id": "rev-1",
                "decision": "adopt",
                "fixture_answer_id": opened["fixture_answer_id"],
            }
            saved = client.post("/api/practice/confirmations", json=body)
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(saved.json()["count"], 1)
            listed = client.get("/api/practice/papers").json()
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["papers"][0]["paper_id"], opened["paper_id"])
            self.assertEqual(client.get("/api/practice/confirmations/count").json()["count"], 1)
            self.assertEqual(store.confirmation_count(), 3)

    def test_confirm_gate_drops_a_late_load_and_retries_the_stored_body(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required for the confirm gate check")
        assert node is not None
        script = (
            "import { startSwitch, cleared, acceptLoad, acceptResponse, retryBody,"
            " showConflictReload, attemptBlock } from './apps/web/src/confirm_gate.js';"
            "const first = startSwitch(0);"
            "const view = cleared();"
            "if (view.attempt !== null || view.confirmAllowed !== false) process.exit(2);"
            "const moved = startSwitch(first);"
            "const late = acceptLoad(first, moved, { answer_text: 'old' });"
            "if (late.apply !== false) process.exit(3);"
            "const failed = acceptLoad(moved, moved, null);"
            "if (failed.confirmAllowed !== false) process.exit(4);"
            "const loaded = acceptLoad(moved, moved, { answer_text: '2' });"
            "if (!loaded.confirmAllowed || loaded.attempt.answer_text !== '2') process.exit(5);"
            "const stored = { decision: 'adopt', operation_key: 'key-web-1' };"
            "const edited = { decision: 'reject', operation_key: 'key-web-9' };"
            "const again = retryBody(stored, edited);"
            "if (again !== stored || again.decision !== 'adopt') process.exit(6);"
            "if (!showConflictReload('version_mismatch') || showConflictReload('unauthorized')) process.exit(7);"
            "const blocked = attemptBlock('attempt_not_current');"
            "if (!blocked || blocked.confirmAllowed !== false || !blocked.notice || !blocked.nextStep) process.exit(8);"
            "if (attemptBlock('unauthorized')) process.exit(9);"
            "const switched = startSwitch(moved);"
            "const lateConfirm = acceptResponse(moved, switched, { confirmation: { confirmation_id: 'A' }, payload: { operation_key: 'key-a' } });"
            "if (lateConfirm.apply !== false || lateConfirm.body) process.exit(10);"
            "const kept = acceptResponse(switched, switched, { confirmation: { confirmation_id: 'B' }, payload: { operation_key: 'key-b' } });"
            "if (!kept.apply || kept.body.payload.operation_key !== 'key-b') process.exit(11);"
            "const storedRetry = retryBody({ operation_key: 'key-web-1', decision: 'adopt' }, null);"
            "if (!storedRetry || storedRetry.decision !== 'adopt') process.exit(12);"
            "console.log('GATE PASS');"
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("GATE PASS", completed.stdout)

    def test_late_handout_keeps_the_open_paper_and_its_confirm_body(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required for the hand-out gate check")
        assert node is not None
        script = (
            "import { startSwitch, cleared, acceptLoad, acceptResponse, takeHandOut,"
            " confirmPayload, retryBody } from './apps/web/src/confirm_gate.js';"
            "let generation = 0;"
            "let view = {"
            " paper: { paper_id: 'A', status: '可打印', student_id: 'student-synth' },"
            " attempt: { answer_text: '学生写下了 5', sub_question_id: 'sq-1',"
            " review_version_id: 'rev-1', fixture_answer_id: 'fixture-answer-A' },"
            " confirmation: { confirmation_id: 'conf-A' },"
            " payload: { operation_key: 'key-a', paper_id: 'A', decision: 'adopt' },"
            " message: '', error: '', errorCode: ''"
            "};"
            "const handToken = generation;"
            "generation = startSwitch(generation);"
            "const blank = cleared();"
            "view = { ...view, paper: { paper_id: 'B', status: '可打印', student_id: 'student-synth-2' },"
            " attempt: blank.attempt, confirmation: blank.confirmation, payload: blank.payload };"
            "const loaded = acceptLoad(generation, generation, {"
            " answer_text: '学生写下了 5', sub_question_id: 'sq-1', review_version_id: 'rev-1',"
            " fixture_answer_id: 'fixture-answer-B' });"
            "if (!loaded.apply) process.exit(2);"
            "view = { ...view, attempt: loaded.attempt, message: '已打开卷 B' };"
            "const stored = confirmPayload(view.paper, view.attempt, 'teacher-synth', 'adopt', 'key-b');"
            "view = { ...view, payload: stored, confirmation: { confirmation_id: 'conf-B' } };"
            "const lateOk = takeHandOut(view, handToken, generation, { paper: { paper_id: 'A', status: '已发放' } });"
            "if (lateOk.apply || lateOk.view.paper.paper_id !== 'B') process.exit(3);"
            "if (lateOk.view.attempt.fixture_answer_id !== 'fixture-answer-B') process.exit(4);"
            "if (lateOk.view.confirmation.confirmation_id !== 'conf-B') process.exit(5);"
            "if (lateOk.view.message !== '已打开卷 B' || lateOk.view.error) process.exit(6);"
            "const sent = confirmPayload(lateOk.view.paper, lateOk.view.attempt, 'teacher-synth', 'adopt', 'key-b');"
            "if (sent.paper_id !== 'B' || sent.fixture_answer_id !== 'fixture-answer-B') process.exit(7);"
            "if (sent.sub_question_id !== lateOk.view.attempt.sub_question_id) process.exit(8);"
            "if (sent.review_version_id !== 'rev-1' || sent.paper_id !== lateOk.view.paper.paper_id) process.exit(9);"
            "const again = retryBody(lateOk.view.payload, { operation_key: 'key-edited', paper_id: 'A', decision: 'reject' });"
            "if (again !== lateOk.view.payload || again.paper_id !== 'B' || again.operation_key !== 'key-b') process.exit(10);"
            "const lateBad = takeHandOut(view, handToken, generation,"
            " { error: { code: 'retired', message: 'publication is retired' } });"
            "if (lateBad.apply || lateBad.view.error || lateBad.view.errorCode) process.exit(11);"
            "if (lateBad.view.paper.paper_id !== 'B' || lateBad.view.attempt.fixture_answer_id !== 'fixture-answer-B') process.exit(12);"
            "const refreshed = acceptResponse(handToken, generation, { papers: [{ paper_id: 'A', status: '已发放' }] });"
            "if (refreshed.apply || refreshed.body) process.exit(13);"
            "const handed = takeHandOut(view, generation, generation, { paper: { status: '已发放' } });"
            "if (!handed.apply || handed.view.paper.paper_id !== 'B' || handed.view.paper.status !== '已发放') process.exit(14);"
            "if (handed.view.attempt.fixture_answer_id !== 'fixture-answer-B') process.exit(15);"
            "if (handed.view.payload.operation_key !== 'key-b' || handed.view.confirmation.confirmation_id !== 'conf-B') process.exit(16);"
            "const after = confirmPayload(handed.view.paper, handed.view.attempt, 'teacher-synth', 'adopt', handed.view.payload.operation_key);"
            "if (after.paper_id !== 'B' || after.fixture_answer_id !== 'fixture-answer-B') process.exit(17);"
            "const failed = takeHandOut(view, generation, generation,"
            " { error: { code: 'retired', message: 'publication is retired' } });"
            "if (!failed.apply || failed.view.paper.paper_id !== 'B') process.exit(18);"
            "if (failed.view.errorCode !== 'retired' || !failed.view.error.includes('publication is retired')) process.exit(19);"
            "if (failed.view.attempt.fixture_answer_id !== 'fixture-answer-B' || failed.view.message !== '') process.exit(20);"
            "console.log('HANDOUT GATE PASS');"
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("HANDOUT GATE PASS", completed.stdout)

    def test_issue_handout_overlap_keeps_the_open_paper(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required for the overlap gate check")
        assert node is not None
        script = (
            "import { startSwitch, cleared, acceptLoad, takeHandOut, confirmPayload,"
            " retryBody, canHandOut, patchHandOutList, confirmReady } from './apps/web/src/confirm_gate.js';"
            "const attemptA = { paper_id: 'A', answer_text: '学生写下了 5', sub_question_id: 'sq-1',"
            " review_version_id: 'rev-1', fixture_answer_id: 'fixture-answer-A' };"
            "const paperA = { paper_id: 'A', status: '可打印', student_id: 'student-synth' };"
            "const paperB = { paper_id: 'B', status: '可打印', student_id: 'student-synth-2' };"
            "const attemptB = { paper_id: 'B', answer_text: '学生写下了 5', sub_question_id: 'sq-1',"
            " review_version_id: 'rev-1', fixture_answer_id: 'fixture-answer-B' };"
            "let generation = 0;"
            "const handToken = generation;"
            "generation = startSwitch(generation);"
            "const blank = cleared();"
            "let switched = { paper: paperB, attempt: blank.attempt, confirmation: null, payload: null,"
            " message: '', error: '', errorCode: '' };"
            "const loadedFirst = acceptLoad(generation, generation, attemptB);"
            "if (!loadedFirst.apply) process.exit(2);"
            "switched = { ...switched, attempt: loadedFirst.attempt };"
            "const lateFirst = takeHandOut(switched, handToken, generation, { paper: { paper_id: 'A', status: '已发放' } });"
            "if (lateFirst.apply || lateFirst.view.paper.paper_id !== 'B') process.exit(2);"
            "const sentFirst = confirmPayload(lateFirst.view.paper, lateFirst.view.attempt, 'teacher-synth', 'adopt', 'key-b');"
            "if (sentFirst.paper_id !== 'B' || sentFirst.fixture_answer_id !== 'fixture-answer-B') process.exit(2);"
            "if (canHandOut(paperA, false) !== true) process.exit(3);"
            "generation = startSwitch(generation);"
            "if (canHandOut(paperA, true) !== false) process.exit(3);"
            "const issued = acceptLoad(generation, generation, attemptB);"
            "if (!issued.apply || !confirmReady(paperB, issued.attempt)) process.exit(4);"
            "let paper = paperB;"
            "let attempt = issued.attempt;"
            "const snapshot = { paper: paperA, attempt: attemptA, confirmation: null, payload: null,"
            " message: '', error: '', errorCode: '' };"
            "const lateOk = takeHandOut(snapshot, generation, generation,"
            " { paper: { paper_id: 'A', status: '已发放' } }, paper.paper_id);"
            "if (lateOk.apply) process.exit(6);"
            "if (paper.paper_id !== 'B') process.exit(7);"
            "if (attempt.fixture_answer_id !== 'fixture-answer-B') process.exit(8);"
            "const sent = confirmPayload(paper, attempt, 'teacher-synth', 'adopt', 'key-b');"
            "if (sent.paper_id !== 'B') process.exit(9);"
            "if (sent.fixture_answer_id !== 'fixture-answer-B') process.exit(10);"
            "let papers = [paperA, paperB];"
            "papers = patchHandOutList(papers, { paper_id: 'A', status: '已发放' });"
            "if (papers[0].status !== '已发放' || papers[0].paper_id !== 'A') process.exit(11);"
            "if (papers[1].paper_id !== 'B' || paper.paper_id !== 'B') process.exit(11);"
            "const stored = sent;"
            "const lateBad = takeHandOut(snapshot, generation, generation,"
            " { error: { code: 'retired', message: 'publication is retired' } }, paper.paper_id);"
            "if (lateBad.apply || lateBad.view.error || lateBad.view.errorCode) process.exit(12);"
            "const again = retryBody(stored, { operation_key: 'key-edited', paper_id: 'A', decision: 'reject' });"
            "if (again !== stored || again.paper_id !== 'B' || again.fixture_answer_id !== 'fixture-answer-B') process.exit(13);"
            "if (canHandOut(paperB, false) !== true) process.exit(14);"
            "const owned = takeHandOut({ ...snapshot, paper: paperB, attempt: attemptB }, generation, generation,"
            " { paper: { paper_id: 'B', status: '已发放' } }, 'B');"
            "if (!owned.apply || owned.view.paper.paper_id !== 'B' || owned.view.paper.status !== '已发放') process.exit(15);"
            "if (owned.view.attempt.fixture_answer_id !== 'fixture-answer-B') process.exit(16);"
            "if (confirmReady({ paper_id: 'A', status: '已发放' }, attemptB) !== false) process.exit(17);"
            "console.log('OVERLAP handout-then-switch paper=B attempt=fixture-answer-B');"
            "console.log('OVERLAP issue-then-handout paper=' + paper.paper_id + ' attempt=' + attempt.fixture_answer_id);"
            "console.log('OVERLAP GATE PASS');"
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("OVERLAP handout-then-switch paper=B attempt=fixture-answer-B", completed.stdout)
        self.assertIn("OVERLAP issue-then-handout paper=B attempt=fixture-answer-B", completed.stdout)
        self.assertIn("OVERLAP GATE PASS", completed.stdout)

    def test_stale_list_keeps_a_confirmed_handout_on_the_open_paper(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required for the stale-list race")
        assert node is not None
        page = (ROOT / "apps/web/src/App.jsx").read_text(encoding="utf-8")
        self.assertIn('from "./paper_loop.js"', page)
        self.assertNotIn("setPapers(listed.body.papers)", page)
        self.assertNotIn("setPapers(nextPapers.papers)", page)
        completed = subprocess.run(
            [node, str(ROOT / "tests" / "list_race.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("LIST RACE A=已发放 open=B attempt=fixture-answer-B confirm=B retry=key-b", completed.stdout)
        self.assertIn("LIST RACE late-error paper=B attempt=fixture-answer-B error=", completed.stdout)
        self.assertIn("LIST RACE PASS", completed.stdout)

    def test_ac02_ac04_issue_then_turn_then_confirm(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required for the issue, turn, and confirm path")
        assert node is not None
        page = (ROOT / "apps/web/src/App.jsx").read_text(encoding="utf-8")
        self.assertIn('from "./paper_state.js"', page)
        self.assertIn("useReducer", page)
        self.assertNotIn("live.current", page)
        completed = subprocess.run(
            [node, str(ROOT / "tests" / "paper_happy.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("HAPPY issue=A turn=B confirm=conf-b", completed.stdout)
        self.assertIn("HAPPY PASS", completed.stdout)

    def test_parallel_revisions_keep_distinct_versions_and_the_old_pdf(self) -> None:
        loop = compose()
        load_fixture(loop)
        published = publish_version("q-v1", loop.approvals, loop.logger, "req-pub")
        self.assertIsInstance(published, Ok)
        issued = issue_paper(
            _command("q-v1"),
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.logger,
            "req-old",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(issued, Ok)
        assert isinstance(issued, Ok)
        drawn = render_paper(
            issued.value.paper_id,
            loop.approvals,
            loop.auth,
            loop.practice,
            loop.files,
            loop.renderer,
            loop.logger,
            "req-draw",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(drawn, Ok)
        assert isinstance(drawn, Ok)
        old_pdf = loop.files.read(drawn.value.file_id or "")
        assert old_pdf is not None
        approvals = BothSeeFree(loop.approvals)
        loop = self._loop(approvals=approvals, practice=loop.practice, auth=loop.auth, files=loop.files, renderer=loop.renderer, logger=loop.logger)
        results: list[Ok[object] | Err | None] = [None, None]
        stems = ("\u8ba1\u7b97\uff1a2\u00d73", "\u8ba1\u7b97\uff1a9+9")
        answers = ("6", "18")

        def work(index: int) -> None:
            results[index] = revise_text(
                "q-v1",
                stems[index],
                answers[index],
                loop.approvals,
                loop.logger,
                "req-race-" + str(index),
            )

        threads = [threading.Thread(target=work, args=(index,)) for index in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertTrue(all(isinstance(item, Ok) for item in results))
        versions = []
        for item in results:
            assert isinstance(item, Ok)
            versions.append(item.value)
        ids = {row.question_version_id for row in versions}
        answer_ids = {row.answer_version_id for row in versions}
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(answer_ids), 2)
        self.assertNotIn("q-v1", ids)
        original = loop.approvals.read_snapshot("q-v1")
        assert original is not None
        self.assertEqual(original.stem, "\u8ba1\u7b97\uff1a(-3)+5")
        self.assertTrue(original.question_approved)
        self.assertTrue(original.answer_approved)
        self.assertEqual(loop.files.read(drawn.value.file_id or ""), old_pdf)
        for row in versions:
            self.assertFalse(row.question_approved)
            self.assertFalse(row.answer_approved)
            blocked = issue_paper(
                _command(row.question_version_id),
                loop.approvals,
                loop.auth,
                loop.practice,
                loop.logger,
                "req-block-" + row.question_version_id,
                actor_teacher_id="teacher-synth",
            )
            self.assertIsInstance(blocked, Err)
            assert isinstance(blocked, Err)
            self.assertEqual(blocked.code, "not_approved")

    def test_a_finished_retirement_is_not_overwritten_by_a_stale_publish(self) -> None:
        loop = compose()
        load_fixture(loop)
        approvals = RetireWins(loop.approvals)
        holder: dict[str, Ok[object] | Err] = {}

        def publish() -> None:
            holder["result"] = publish_version("q-v1", approvals, loop.logger, "req-stale-publish")

        thread = threading.Thread(target=publish)
        thread.start()
        self.assertTrue(approvals.publish_waiting.wait(timeout=5))
        from backend.catalog.application.publish_version import retire_version

        retired = retire_version("q-v1", approvals, loop.logger, "req-retire")
        approvals.allow_publish.set()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(retired, Ok)
        result = holder["result"]
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "retired")
        stored = approvals.read_snapshot("q-v1")
        assert stored is not None
        self.assertTrue(stored.retired)
        self.assertFalse(stored.question_approved)

    def test_refresh_reads_the_current_review_or_refuses(self) -> None:
        with self._client() as client:
            self._publish(client)
            opened = self._issue(client, "student-synth")
            paper_id = str(opened["paper_id"])
            current = client.get("/api/practice/papers/" + paper_id + "/attempt")
            self.assertEqual(current.status_code, 200)
            self.assertEqual(current.json()["review_version_id"], "rev-1")
            self.assertEqual(current.json()["answer_text"], "\u5b66\u751f\u5199\u4e0b\u4e86 5")
            store = client.app.state.loop.practice
            store.set_review_version(paper_id, "rev-2")
            missing = client.get("/api/practice/papers/" + paper_id + "/attempt")
            self.assertEqual(missing.status_code, 409)
            self.assertEqual(missing.json()["code"], "attempt_not_current")
            store.put_answer(
                PendingAnswer(
                    fixture_answer_id="fixture-answer-rev2",
                    paper_id=paper_id,
                    sub_question_id="sq-1",
                    review_version_id="rev-2",
                    student_id="student-synth",
                    status="pending",
                    answer_text="\u53e6\u4e00\u7248\u4f5c\u7b54",
                )
            )
            refreshed = client.get("/api/practice/papers/" + paper_id + "/attempt")
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["review_version_id"], "rev-2")
            self.assertEqual(refreshed.json()["answer_text"], "\u53e6\u4e00\u7248\u4f5c\u7b54")
            self.assertNotEqual(refreshed.json()["answer_text"], "2")

    def _client(self, loop: Loop | None = None):  # type: ignore[no-untyped-def]
        return signed_client(loop)

    def _loop(self, **overrides: object) -> Loop:
        base = compose()
        values: dict[str, object] = {
            "approvals": base.approvals,
            "practice": base.practice,
            "auth": base.auth,
            "logger": base.logger,
            "files": base.files,
            "renderer": base.renderer,
            "health": base.health,
        }
        values.update(overrides)
        return Loop(**values)  # type: ignore[arg-type]

    def _publish(self, client: TestClient) -> None:
        response = client.post("/api/catalog/q-v1/publish")
        self.assertEqual(response.status_code, 200, response.text)

    def _issue(self, client: TestClient, student_id: str) -> dict[str, object]:
        response = client.post("/api/practice/papers", json=dict(ISSUE, student_id=student_id))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _pdf(self, client: TestClient, file_id: str) -> bytes:
        response = client.get("/api/practice/files/" + file_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.content


class BothSeeFree(MemoryApprovals):
    """Both revisions observe q-v2 as free before either insert."""

    def __init__(self, source: MemoryApprovals) -> None:
        super().__init__()
        self._items = source._items
        self.both = threading.Barrier(2)

    def has_version_id(self, version_id: str) -> bool:
        seen = super().has_version_id(version_id)
        if version_id == "q-v2" and not seen:
            self.both.wait(timeout=5)
        return seen


class RetireWins(MemoryApprovals):
    """Hold the first publish write until retire has stored its snapshot."""

    def __init__(self, source: MemoryApprovals) -> None:
        super().__init__()
        self._items = source._items
        self.publish_waiting = threading.Event()
        self.allow_publish = threading.Event()

    def replace_if_current(self, expected: object, updated: object) -> bool:
        from backend.catalog.domain.snapshot import ApprovalSnapshot

        assert isinstance(expected, ApprovalSnapshot)
        assert isinstance(updated, ApprovalSnapshot)
        if updated.question_approved and not updated.retired and not self.publish_waiting.is_set():
            self.publish_waiting.set()
            if not self.allow_publish.wait(timeout=5):
                raise TimeoutError("retire did not release the stale publish")
        return super().replace_if_current(expected, updated)


def _command(question_version_id: str) -> IssuePaperCommand:
    return IssuePaperCommand(
        teacher_id="teacher-synth",
        student_id="student-synth",
        subject_id="math",
        question_version_id=question_version_id,
        review_version_id="rev-1",
    )


def _page(formula: str) -> PaperPage:
    return PaperPage(
        question_version_id="q-v1",
        answer_version_id="a-v1",
        formula=formula,
        student_id="student-synth",
        page_number=1,
        item_order=("sq-1",),
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        paper_id="paper-1",
        page_count=1,
    )


def _stored_paper(paper_id: str, teacher_id: str, student_id: str) -> Paper:
    frozen = freeze_paper(
        paper_id=paper_id,
        teacher_id=teacher_id,
        student_id=student_id,
        subject_id="math",
        question_version_id="q-v1",
        answer_version_id="a-v1",
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        review_version_id="rev-1",
        item_order=("sq-1",),
        formula="(-3)+5",
    )
    if isinstance(frozen, Err):
        raise AssertionError(frozen.code)
    return frozen


def _confirm(store: MemoryPractice, paper: Paper, confirmation_id: str, key: str, teacher_id: str) -> None:
    answer_id = "fixture-answer-" + paper.paper_id
    store.put_answer(
        PendingAnswer(
            fixture_answer_id=answer_id,
            paper_id=paper.paper_id,
            sub_question_id="sq-1",
            review_version_id="rev-1",
            student_id=paper.student_id,
            status="pending",
            answer_text="2",
        )
    )
    saved = store.commit_confirmation(
        Confirmation(
            confirmation_id=confirmation_id,
            operation_key=OperationKey(key),
            paper_id=paper.paper_id,
            sub_question_id="sq-1",
            teacher_id=teacher_id,
            review_version_id="rev-1",
            decision="adopt",
            fixture_answer_id=answer_id,
        )
    )
    if isinstance(saved, Err):
        raise AssertionError(saved.code)


if __name__ == "__main__":
    unittest.main()
