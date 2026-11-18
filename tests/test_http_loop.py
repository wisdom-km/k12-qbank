"""HTTP loop on synthetic data. The actor is the server context."""

from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from backend.bootstrap.compose import Loop, compose
from backend.bootstrap.stdout_log import StdoutLogger
from http_client import signed_client
from backend.kernel.result import Err
from backend.practice.adapters.memory import MemoryPractice


ISSUE = {
    "teacher_id": "teacher-synth",
    "student_id": "student-synth",
    "subject_id": "math",
    "question_version_id": "q-v1",
    "review_version_id": "rev-1",
}


class BoomStore(MemoryPractice):
    def place_issued(self, paper: object, answer: object) -> None:
        raise RuntimeError("synthetic store fault")


class BadRenderer:
    def render(self, page: object) -> Err:
        return Err("not_rendered", "draw failed")


class HttpLoopTest(unittest.TestCase):
    def test_health_is_status_only(self) -> None:
        with self._client() as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_unapproved_retired_and_unauthorized_write_nothing(self) -> None:
        with self._client() as client:
            self.assertEqual(client.get("/api/catalog/q-v1").json()["question_approved"], False)
            refused = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(refused.status_code, 409)
            self.assertEqual(refused.json()["code"], "not_approved")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)
            self._publish(client)
            stranger = dict(ISSUE, student_id="student-other")
            other = client.post("/api/practice/papers", json=stranger)
            self.assertEqual(other.json()["code"], "unauthorized")
            subject = client.post("/api/practice/papers", json=dict(ISSUE, subject_id="science"))
            self.assertEqual(subject.json()["code"], "subject_mismatch")
            retired = client.post("/api/catalog/q-v1/retire")
            self.assertEqual(retired.json()["retired"], True)
            again = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(again.json()["code"], "retired")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)

    def test_publish_issue_pdf_and_old_bytes_survive_a_bank_edit(self) -> None:
        with self._client() as client:
            self._publish(client)
            first = self._issue(client, "student-synth")
            second = self._issue(client, "student-synth-2")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 2)
            self.assertNotEqual(first["paper_id"], second["paper_id"])
            self.assertNotEqual(first["file_checksum"], second["file_checksum"])
            self.assertEqual(first["status"], "可打印")
            first_pdf = client.get("/api/practice/files/" + first["file_id"]).content
            second_pdf = client.get("/api/practice/files/" + second["file_id"]).content
            self.assertIn(b"\\(-3\\)+5", first_pdf)
            self.assertIn(b"student-synth", first_pdf)
            self.assertNotIn(b"student-synth-2", first_pdf)
            self.assertIn(b"student-synth-2", second_pdf)
            self.assertIn(b"page 1", first_pdf)
            self.assertIn(b"pages 1", first_pdf)
            self.assertIn(("paper " + str(first["paper_id"])).encode(), first_pdf)
            self.assertNotIn(str(second["paper_id"]).encode(), first_pdf)
            self.assertIn(b"name-rule omit", first_pdf)
            self.assertNotIn(b"answer ", first_pdf)
            self.assertEqual(hashlib_sha(first_pdf), first["file_checksum"])
            edited = client.post(
                "/api/catalog/q-v1/revise",
                json={"stem": "计算：(-9)+9", "answer_text": "0"},
            )
            self.assertEqual(edited.status_code, 200)
            self.assertEqual(edited.json()["question_version_id"], "q-v2")
            self.assertEqual(edited.json()["answer_version_id"], "a-v2")
            self.assertEqual(edited.json()["question_approved"], False)
            self.assertEqual(edited.json()["answer_approved"], False)
            original = client.get("/api/catalog/q-v1").json()
            self.assertEqual(original["stem"], "计算：(-3)+5")
            self.assertEqual(original["answer_text"], "2")
            self.assertEqual(original["question_approved"], True)
            again = client.get("/api/practice/files/" + first["file_id"]).content
            self.assertEqual(again, first_pdf)
            listed = client.get("/api/practice/papers").json()["papers"]
            stored = next(row for row in listed if row["paper_id"] == first["paper_id"])
            self.assertEqual(stored["file_id"], first["file_id"])
            self.assertEqual(stored["file_checksum"], first["file_checksum"])
            self.assertEqual(stored["question_version_id"], "q-v1")
            client.app.state.loop.files._items[first["file_id"]] = first_pdf + b"\n"
            changed = client.get("/api/practice/files/" + first["file_id"])
            self.assertEqual(changed.status_code, 409)
            self.assertEqual(changed.json()["code"], "file_changed")
            listed_after = client.get("/api/practice/papers").json()["papers"]
            kept = next(row for row in listed_after if row["paper_id"] == first["paper_id"])
            self.assertEqual(kept["file_id"], first["file_id"])

    def test_render_failure_stays_waiting_and_retirement_blocks_handout(self) -> None:
        waiting = self._loop(renderer=BadRenderer())
        with self._client(waiting) as client:
            self._publish(client)
            opened = self._issue(client, "student-synth")
            self.assertEqual(opened["status"], "待渲染")
            self.assertIsNone(opened["file_id"])
            self.assertEqual(opened["render_code"], "not_rendered")
            self.assertEqual(opened["render_message"], "draw failed")
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 1)
        with self._client() as client:
            self._publish(client)
            opened = self._issue(client, "student-synth")
            handed = client.post("/api/practice/papers/" + opened["paper_id"] + "/handout")
            self.assertEqual(handed.status_code, 200)
            self.assertEqual(handed.json()["status"], "已发放")
            self.assertEqual(handed.json()["file_id"], opened["file_id"])
            second = self._issue(client, "student-synth-2")
            client.post("/api/catalog/q-v1/retire")
            blocked = client.post("/api/practice/papers/" + second["paper_id"] + "/handout")
            self.assertEqual(blocked.status_code, 409)
            self.assertEqual(blocked.json()["code"], "retired")
            rows = client.get("/api/practice/papers").json()["papers"]
            kept = next(row for row in rows if row["paper_id"] == second["paper_id"])
            self.assertEqual(kept["status"], "可打印")
            self.assertEqual(kept["file_id"], second["file_id"])

    def test_confirm_replay_conflict_and_stale_version(self) -> None:
        with self._client() as client:
            self._publish(client)
            opened = self._issue(client, "student-synth")
            attempt = client.get("/api/practice/papers/" + opened["paper_id"] + "/attempt")
            self.assertEqual(attempt.status_code, 200)
            self.assertEqual(attempt.json()["answer_text"], "学生写下了 5")
            self.assertNotEqual(attempt.json()["answer_text"], "2")
            body = {
                "operation_key": "key-web-1",
                "paper_id": opened["paper_id"],
                "sub_question_id": attempt.json()["sub_question_id"],
                "teacher_id": "teacher-synth",
                "review_version_id": attempt.json()["review_version_id"],
                "decision": "adopt",
                "fixture_answer_id": attempt.json()["fixture_answer_id"],
            }
            first = client.post("/api/practice/confirmations", json=body)
            replay = client.post("/api/practice/confirmations", json=body)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(replay.json()["confirmation_id"], first.json()["confirmation_id"])
            self.assertEqual(client.get("/api/practice/confirmations/count").json()["count"], 1)
            changed = dict(body, decision="reject")
            mismatch = client.post("/api/practice/confirmations", json=changed)
            self.assertEqual(mismatch.json()["code"], "key_content_mismatch")
            self.assertEqual(client.get("/api/practice/confirmations/count").json()["count"], 1)
            stranger = dict(body, teacher_id="teacher-b", operation_key="key-web-2")
            denied = client.post("/api/practice/confirmations", json=stranger)
            self.assertEqual(denied.json()["code"], "confirm_conflict")
            self.assertNotIn("confirmation_id", denied.json())
            stored = client.app.state.loop.practice.list_confirmations()
            self.assertEqual(stored[0].teacher_id, "teacher-synth")
        with self._client() as client:
            self._publish(client)
            opened = self._issue(client, "student-synth")
            attempt = client.get("/api/practice/papers/" + opened["paper_id"] + "/attempt").json()
            client.app.state.loop.practice.set_review_version(opened["paper_id"], "rev-2")
            stale = client.post(
                "/api/practice/confirmations",
                json={
                    "operation_key": "key-web-stale",
                    "paper_id": opened["paper_id"],
                    "sub_question_id": attempt["sub_question_id"],
                    "teacher_id": "teacher-synth",
                    "review_version_id": attempt["review_version_id"],
                    "decision": "adopt",
                    "fixture_answer_id": attempt["fixture_answer_id"],
                },
            )
            self.assertEqual(stale.json()["code"], "version_mismatch")
            orphan = client.post(
                "/api/practice/confirmations",
                json={
                    "operation_key": "key-web-orphan",
                    "paper_id": opened["paper_id"],
                    "sub_question_id": attempt["sub_question_id"],
                    "teacher_id": "teacher-synth",
                    "review_version_id": "rev-2",
                    "decision": "adopt",
                    "fixture_answer_id": "fixture-answer-missing",
                },
            )
            self.assertEqual(orphan.json()["code"], "answer_not_owned")
            self.assertEqual(client.get("/api/practice/confirmations/count").json()["count"], 0)

    def test_store_fault_shares_one_request_id(self) -> None:
        lines: list[str] = []
        loop = self._loop(practice=BoomStore(), logger=StdoutLogger(sink=lines.append))
        with self._client(loop) as client:
            self._publish(client)
            response = client.post(
                "/api/practice/papers",
                json=ISSUE,
                headers={"X-Request-Id": "drill-http-1"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "store_failed")
        self.assertEqual(response.json()["request_id"], "drill-http-1")
        self.assertEqual(loop.practice.paper_count(), 0)
        events = [json.loads(line) for line in lines]
        matched = [row for row in events if row["request_id"] == "drill-http-1"]
        names = {row["event"] for row in matched}
        self.assertIn("use_case_failed", names)
        self.assertIn("http_completed", names)
        self.assertTrue(all("student" not in row["outcome"] for row in matched))

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
        body = response.json()
        self.assertEqual(body["question_approved"], True)
        self.assertEqual(body["answer_approved"], True)

    def _issue(self, client: TestClient, student_id: str) -> dict[str, object]:
        response = client.post("/api/practice/papers", json=dict(ISSUE, student_id=student_id))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


def hashlib_sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    unittest.main()
