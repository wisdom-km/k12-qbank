"""Lesson list over HTTP. A signed-in teacher can read it. An unknown book is 404."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET

ADMIN_USER = "admin"
ADMIN_SECRET = "admin-pass1"
ADMIN_NEXT = "admin-pass2"
_BOOK = "synth-r4f-http"


class BookLessonsHttpTest(unittest.TestCase):
    def test_lessons_group_an_imported_book_and_count_only_published_questions(self) -> None:
        app = _app()
        with TestClient(app) as client:
            missing = client.get("/api/catalog/books/synth-r4f-missing/lessons")
            self.assertEqual(missing.status_code, 401)
            token = _login_admin(client)
            saved = client.post(
                "/api/admin/catalog/books/" + _BOOK + "/import",
                json=_body(),
                headers={"X-K12-CSRF": token},
            )
            self.assertEqual(saved.status_code, 200, saved.text)
            report = saved.json()
            self.assertTrue(report["written"])
            self.assertEqual(report["toc_lessons"], 1)
            self.assertEqual(report["questions"][0]["lesson_order"], 1)
            question_id = report["questions"][0]["question_version_id"]
            listed = client.get("/api/catalog/books/" + _BOOK + "/lessons")
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(_count(listed.json()), 0)
            published = client.post(
                "/api/catalog/" + question_id + "/publish",
                headers={"X-K12-CSRF": token},
            )
            self.assertEqual(published.status_code, 200, published.text)
            teacher = client.post(
                "/api/login",
                json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET},
            )
            self.assertEqual(teacher.status_code, 200, teacher.text)
            ready = client.get("/api/catalog/books/" + _BOOK + "/lessons")
            self.assertEqual(ready.status_code, 200, ready.text)
            body = ready.json()
            self.assertEqual(body["book_id"], _BOOK)
            self.assertEqual(body["chapters"][0]["title"], "一、synth-ch")
            self.assertEqual(body["chapters"][0]["sections"][0]["title"], "synth-sec")
            self.assertEqual(_count(body), 1)
            absent = client.get("/api/catalog/books/synth-r4f-missing/lessons")
            self.assertEqual(absent.status_code, 404)
            self.assertEqual(absent.json()["code"], "not_found")
            catalog = client.get("/api/catalog")
            row = next(item for item in catalog.json()["items"] if item["question_version_id"] == question_id)
            self.assertEqual(row["book_id"], _BOOK)
            self.assertEqual(row["lesson_order"], 1)
            self.assertEqual(row["lesson_title"], "synth-les")


def _app() -> object:
    with mock.patch.dict(
        os.environ,
        {
            "K12_BOOTSTRAP_ADMIN_USERNAME": ADMIN_USER,
            "K12_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_SECRET,
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


def _body() -> dict[str, object]:
    page = _qpage(1, "1:1", "synth-http", "synth-a")
    page["volume"] = "questions"
    return {
        "subject_id": "math",
        "dry_run": False,
        "pages": [page],
        "pairing": [],
        "toc": [{"pdf_page": 1, "text": "## 一、synth-ch\nsynth-sec\nsynth-les \u2026 1\n"}],
        "toc_page_offset": 0,
    }


def _count(body: dict[str, object]) -> int:
    chapters = body["chapters"]
    assert isinstance(chapters, list)
    return int(chapters[0]["sections"][0]["lessons"][0]["issuable_count"])  # type: ignore[index]


def _qpage(page: int, key: str, stem: str, answer: str) -> dict[str, object]:
    return {
        "pdf_page": page,
        "role": "questions",
        "questions": {
            "contract": "k12-question-draft",
            "contract_version": 1,
            "schema_version": 1,
            "ok": True,
            "reason": "",
            "preface": "",
            "source": {"pdf_page": page},
            "questions": [
                {
                    "key": key,
                    "section": "一",
                    "number": "1",
                    "type": "single_choice",
                    "structure": "choice",
                    "status": "confirmed",
                    "stem": [{"type": "text", "value": stem}],
                    "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
                    "subquestions": [],
                    "assets": [],
                    "geometry": None,
                }
            ],
        },
        "answers": [
            {
                "contract": "k12-answer-draft",
                "contract_version": 1,
                "schema_version": 1,
                "ok": True,
                "reason": "",
                "question_key": key,
                "key": key + ":ocr:1",
                "origin": "ocr",
                "status": "confirmed",
                "applicable": True,
                "source": {"pdf_page": page},
                "content": [{"type": "text", "value": answer}],
                "parts": [],
                "assets": [],
            }
        ],
    }
