"""Admin import stages unpublished questions. A teacher reviews them one by one."""

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


class CatalogImportHttpTest(unittest.TestCase):
    def test_admin_import_stages_questions_and_a_second_import_keeps_them(self) -> None:
        app = _app()
        with TestClient(app) as client:
            token = _login_admin(client)
            gone = client.post("/api/admin/catalog/drafts", json=_body(), headers=_csrf(token))
            self.assertEqual(gone.status_code, 404, gone.text)
            created = client.post(_IMPORT, json=_body(), headers=_csrf(token))
            self.assertEqual(created.status_code, 200, created.text)
            staged = [row["question_version_id"] for row in created.json()["questions"] if row["outcome"] == "staged"]
            skipped = [row["original_key"] for row in created.json()["questions"] if row["outcome"] == "skipped"]
            self.assertEqual(staged, ["qv-synth-r3.p0001-r3-1", "qv-synth-r3.p0001-r3-2"])
            self.assertEqual(skipped, ["r3:3"])
            self.assertEqual(created.json()["questions"][0]["key"], "synth-r3.p0001:r3:1")
            self.assertNotIn("计算", created.text)
            listed = client.get("/api/catalog")
            ids = [row["question_version_id"] for row in listed.json()["items"]]
            self.assertLess(ids.index("qv-synth-r3.p0001-r3-1"), ids.index("qv-synth-r3.p0001-r3-2"))
            published = client.post("/api/catalog/qv-synth-r3.p0001-r3-1/publish", headers=_csrf(token))
            self.assertEqual(published.status_code, 200, published.text)
            self.assertTrue(published.json()["question_approved"])
            again = client.post(_IMPORT, json=_body(), headers=_csrf(token))
            self.assertEqual(again.status_code, 200, again.text)
            kept_ids = [row["question_version_id"] for row in again.json()["questions"] if row["outcome"] == "kept"]
            self.assertEqual(again.json()["staged"], 0)
            self.assertEqual(kept_ids, ["qv-synth-r3.p0001-r3-1", "qv-synth-r3.p0001-r3-2"])
            kept = client.get("/api/catalog/qv-synth-r3.p0001-r3-1")
            self.assertTrue(kept.json()["question_approved"])
            self.assertEqual(kept.json()["stem"], "计算：(-3)+5")

    def test_teacher_sees_the_list_and_cannot_import(self) -> None:
        app = _app()
        with TestClient(app) as client:
            admin_token = _login_admin(client)
            created = client.post(_IMPORT, json=_body(), headers=_csrf(admin_token))
            self.assertEqual(created.status_code, 200, created.text)
            teacher = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
            self.assertEqual(teacher.status_code, 200, teacher.text)
            teacher_token = teacher.json()["csrf_token"]
            listed = client.get("/api/catalog")
            ids = [row["question_version_id"] for row in listed.json()["items"]]
            self.assertIn("qv-synth-r3.p0001-r3-1", ids)
            self.assertIn("q-v1", ids)
            refused = client.post(_IMPORT, json=_body(), headers=_csrf(teacher_token))
            self.assertEqual(refused.status_code, 403, refused.text)
            self.assertEqual(refused.json()["code"], "permission_denied")
            missing_csrf = client.post(_IMPORT, json=_body())
            self.assertEqual(missing_csrf.status_code, 403, missing_csrf.text)
            self.assertEqual(missing_csrf.json()["code"], "csrf")


def _app() -> object:
    with mock.patch.dict(
        os.environ,
        {
            "K12_BOOTSTRAP_ADMIN_USERNAME": ADMIN_USER,
            "K12_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_SECRET,
            "K12_LOG_FILE": "0",
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


def _csrf(token: str) -> dict[str, str]:
    return {"X-K12-CSRF": token}


_IMPORT = "/api/admin/catalog/books/synth-r3/import"


def _body() -> dict[str, object]:
    return {
        "subject_id": "math",
        "dry_run": False,
        "pairing": [],
        "pages": [
            {
                "pdf_page": 1,
                "role": "questions",
                "questions": {
                    "contract": "k12-question-draft",
                    "contract_version": 1,
                    "schema_version": 1,
                    "ok": True,
                    "reason": "",
                    "preface": "",
                    "source": {"pdf_page": 1},
                    "questions": [_question("r3:1", "1"), _question("r3:2", "2"), _question("r3:3", "3")],
                },
                "answers": [_answer("r3:1"), _answer("r3:2")],
            }
        ],
    }


def _question(key: str, number: str) -> dict[str, object]:
    return {
        "key": key,
        "section": "一",
        "number": number,
        "type": "single_choice",
        "structure": "choice",
        "status": "confirmed",
        "stem": [{"type": "text", "value": "计算："}, {"type": "math", "latex": "(-3)+5"}],
        "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
        "subquestions": [],
        "assets": [],
        "geometry": None,
    }


def _answer(question_key: str) -> dict[str, object]:
    return {
        "contract": "k12-answer-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "question_key": question_key,
        "key": question_key + ":ocr:1",
        "origin": "ocr",
        "status": "confirmed",
        "applicable": True,
        "source": {"pdf_page": 1},
        "content": [{"type": "text", "value": "2"}],
        "parts": [],
        "assets": [],
    }
