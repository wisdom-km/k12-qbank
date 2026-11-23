"""HTTP issues two approved questions onto one paper. The face keeps the issue-time copy."""

from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest import mock

from http_client import signed_client

ISSUE = {
    "teacher_id": "teacher-synth",
    "student_id": "student-synth",
    "subject_id": "math",
    "question_version_id": "q-v1",
    "review_version_id": "rev-1",
}


class MultiPaperHttpTest(unittest.TestCase):
    def test_two_approved_items_print_one_page_each_and_keep_the_snapshot(self) -> None:
        with mock.patch.dict(os.environ, {"K12_PAPER_QR": "on"}):
            with signed_client() as client:
                self._publish(client, "q-v1")
                revised = client.post(
                    "/api/catalog/q-v1/revise",
                    json={"stem": "计算：2\u00d73", "answer_text": "synth-ans-keep"},
                )
                self.assertEqual(revised.status_code, 200, revised.text)
                second_id = revised.json()["question_version_id"]
                self.assertNotEqual(second_id, "q-v1")
                self._publish(client, second_id)
                opened = client.post(
                    "/api/practice/papers",
                    json=dict(
                        ISSUE,
                        items=[
                            {"question_version_id": "q-v1"},
                            {"question_version_id": second_id},
                        ],
                    ),
                )
                self.assertEqual(opened.status_code, 200, opened.text)
                body = opened.json()
                self.assertTrue(body["qr_printed"])
                self.assertNotIn("synth-0001", opened.text)
                self.assertNotIn("printed_external_id", opened.text)
                self.assertEqual(body["student_id"], "student-synth")
                pdf = client.get("/api/practice/files/" + body["file_id"]).content
                self.assertIn(b"/Count 2", pdf)
                self.assertIn(b"page 2", pdf)
                self.assertIn(b"pages 2", pdf)
                self.assertIn(b"synth-0001", pdf)
                self.assertNotIn(b"student-synth", pdf)
                self.assertNotIn(b"synth-ans-keep", pdf)
                self.assertNotIn(str(body["paper_id"]).encode(), pdf)
                self.assertIn(b"72 220 451 220 re S", pdf)
                self.assertIn(b"formula \\(-3\\)+5", pdf)
                self.assertIn("formula 2\u00d73".encode("cp1252"), pdf)
                on_marks = pdf.count(b" re f")
                frozen = client.app.state.loop.items.items_of(body["paper_id"])
                self.assertEqual([item.stem_text for item in frozen], ["计算：(-3)+5", "计算：2\u00d73"])
                self.assertEqual(frozen[1].answer_text, "synth-ans-keep")
                live = client.app.state.loop.approvals.read_snapshot("q-v1")
                assert live is not None
                client.app.state.loop.approvals.put(replace(live, stem="计算：9+9", answer_text="18"))
                again = client.get("/api/practice/files/" + body["file_id"]).content
                self.assertEqual(again, pdf)
                kept = client.app.state.loop.items.items_of(body["paper_id"])
                self.assertEqual(kept[0].stem_text, "计算：(-3)+5")
                refused = client.post(
                    "/api/practice/papers",
                    json=dict(
                        ISSUE,
                        items=[
                            {"question_version_id": "q-v1"},
                            {"question_version_id": "q-missing"},
                        ],
                    ),
                )
                self.assertEqual(refused.status_code, 409)
                self.assertEqual(refused.json()["code"], "question_not_approved")
                self.assertEqual(client.get("/api/practice/papers").json()["count"], 1)
        with mock.patch.dict(os.environ, {"K12_PAPER_QR": "off"}):
            with signed_client() as client:
                self._publish(client, "q-v1")
                revised = client.post(
                    "/api/catalog/q-v1/revise",
                    json={"stem": "计算：2\u00d73", "answer_text": "synth-ans-keep"},
                )
                second_id = revised.json()["question_version_id"]
                self._publish(client, second_id)
                quiet = client.post(
                    "/api/practice/papers",
                    json=dict(
                        ISSUE,
                        items=[
                            {"question_version_id": "q-v1"},
                            {"question_version_id": second_id},
                        ],
                    ),
                )
                self.assertEqual(quiet.status_code, 200, quiet.text)
                self.assertFalse(quiet.json()["qr_printed"])
                quiet_pdf = client.get("/api/practice/files/" + quiet.json()["file_id"]).content
                self.assertIn(b"/Count 2", quiet_pdf)
                self.assertLess(quiet_pdf.count(b" re f"), on_marks)

    def _publish(self, client: object, question_version_id: str) -> None:
        response = client.post("/api/catalog/" + question_version_id + "/publish")  # type: ignore[attr-defined]
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["question_approved"], True)
        self.assertEqual(response.json()["answer_approved"], True)
