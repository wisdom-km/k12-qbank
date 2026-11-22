"""HTTP issue reads the publication ledger. Retired and missing rows are refused."""

from __future__ import annotations

import unittest
from dataclasses import replace

from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.catalog.api import Publication
from http_client import signed_client


ISSUE = {
    "teacher_id": "teacher-synth",
    "student_id": "student-synth",
    "subject_id": "math",
    "question_version_id": "q-v1",
    "review_version_id": "rev-1",
}


class HttpPublicationTest(unittest.TestCase):
    def test_http_issue_passes_when_publication_active(self) -> None:
        with signed_client() as client:
            self._publish(client)
            active = client.app.state.loop.publications.active_of("q-v1", "a-v1")
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.publication_id, "pub-q-v1-a-v1")
            self.assertEqual(active.status, "active")
            opened = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(opened.status_code, 200, opened.text)
            body = opened.json()
            self.assertEqual(body["question_version_id"], "q-v1")
            self.assertEqual(body["answer_version_id"], "a-v1")
            self.assertEqual(body["status"], "可打印")

    def test_http_issue_rejects_when_publication_retired(self) -> None:
        with signed_client() as client:
            self._publish(client)
            current = client.app.state.loop.publications.active_of("q-v1", "a-v1")
            self.assertIsNotNone(current)
            assert current is not None
            client.app.state.loop.publications.put(
                Publication(
                    publication_id=current.publication_id,
                    question_version_id=current.question_version_id,
                    answer_version_id=current.answer_version_id,
                    subject_id=current.subject_id,
                    status="retired",
                )
            )
            refused = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(refused.status_code, 409)
            self.assertEqual(refused.json()["code"], "no_active_publication")
            self.assertEqual(set(refused.json()), {"code", "message", "request_id"})
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)

    def test_http_issue_rejects_when_publication_absent(self) -> None:
        with signed_client() as client:
            self._publish(client)
            client.app.state.loop = replace(client.app.state.loop, publications=MemoryPublications())
            refused = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(refused.status_code, 409)
            self.assertEqual(refused.json()["code"], "no_active_publication")
            self.assertEqual(set(refused.json()), {"code", "message", "request_id"})
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)

    def _publish(self, client: object) -> None:
        response = client.post("/api/catalog/q-v1/publish")  # type: ignore[attr-defined]
        self.assertEqual(response.status_code, 200, response.text)
