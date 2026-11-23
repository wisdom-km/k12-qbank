"""Imported drafts become unpublished snapshots. Memory always runs. PostgreSQL runs when K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest
from dataclasses import replace

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.stage_review import stage_review
from backend.catalog.domain.answer import parse_answer_draft
from backend.catalog.domain.parse import parse_question_draft
from backend.kernel.result import Ok


class ReviewStageCases:
    approvals: object

    def test_applicable_answers_stage_in_key_order_and_a_missing_answer_is_skipped(self) -> None:
        staged = stage_review(_draft(), _answers(), self.approvals, "math")
        self.assertEqual(staged.staged, ("qv-r3-1", "qv-r3-2"))
        self.assertEqual(staged.kept, ())
        self.assertEqual(staged.skipped, ("r3:3",))
        rows = self.approvals.list_snapshots()  # type: ignore[attr-defined]
        ids = [row.question_version_id for row in rows]
        self.assertLess(ids.index("qv-r3-1"), ids.index("qv-r3-2"))
        first = self.approvals.read_snapshot("qv-r3-1")  # type: ignore[attr-defined]
        self.assertEqual(first.subject_id, "math")
        self.assertEqual(first.stem, "计算：(-3)+5")
        self.assertEqual(first.answer_text, "2")
        self.assertFalse(first.question_approved)
        self.assertFalse(first.answer_approved)
        self.assertEqual(first.answer_version_id, "av-r3-1-ocr-1")

    def test_a_second_stage_keeps_the_stored_snapshot(self) -> None:
        stage_review(_draft(), _answers(), self.approvals, "math")
        current = self.approvals.read_snapshot("qv-r3-1")  # type: ignore[attr-defined]
        self.approvals.put(replace(current, stem="kept-stem"))  # type: ignore[attr-defined]
        again = stage_review(_draft(), _answers(), self.approvals, "math")
        self.assertEqual(again.staged, ())
        self.assertEqual(again.kept, ("qv-r3-1", "qv-r3-2"))
        kept = self.approvals.read_snapshot("qv-r3-1")  # type: ignore[attr-defined]
        self.assertEqual(kept.stem, "kept-stem")


class MemoryReviewStageTest(ReviewStageCases, unittest.TestCase):
    def setUp(self) -> None:
        self.approvals = MemoryApprovals()


class PgReviewStageTest(ReviewStageCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_approvals import PgApprovals

        self.pool = _pool()
        _execute(
            self.pool,
            "DELETE FROM approvals WHERE question_version_id IN ('qv-r3-1', 'qv-r3-2')",
        )
        self.approvals = PgApprovals(self.pool)

    def tearDown(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            return
        _execute(
            self.pool,
            "DELETE FROM approvals WHERE question_version_id IN ('qv-r3-1', 'qv-r3-2')",
        )


_POOL: object | None = None


def _pool() -> object:
    global _POOL
    if _POOL is not None:
        return _POOL
    from psycopg_pool import ConnectionPool

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import migrate

    dsn = os.environ["K12_PG_DSN"]
    migrate(dsn, repo_root(), "up")
    _POOL = ConnectionPool(dsn, min_size=1, max_size=2, open=True)
    return _POOL


def _execute(pool: object, statement: str) -> None:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement)


def _draft() -> object:
    parsed = parse_question_draft(
        {
            "contract": "k12-question-draft",
            "contract_version": 1,
            "schema_version": 1,
            "ok": True,
            "reason": "",
            "preface": "",
            "source": {"pdf_page": 1},
            "questions": [_question("r3:1", "1"), _question("r3:2", "2"), _question("r3:3", "3")],
        }
    )
    if not isinstance(parsed, Ok):
        raise AssertionError(parsed.code)
    return parsed.value


def _answers() -> tuple[object, object]:
    return (_answer("r3:1"), _answer("r3:2"))


def _answer(question_key: str) -> object:
    parsed = parse_answer_draft(
        {
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
    )
    if not isinstance(parsed, Ok):
        raise AssertionError(parsed.code)
    return parsed.value


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
