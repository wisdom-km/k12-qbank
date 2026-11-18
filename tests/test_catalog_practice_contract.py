"""One contract for catalog and practice stores. Memory always runs. PostgreSQL runs when K12_PG_DSN is set."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.result import Err, StoreFault
from backend.kernel.use_log import read_store
from backend.practice.adapters.files import MemoryFiles
from backend.practice.adapters.memory import MemoryPractice
from backend.practice.domain.confirm import Confirmation, OperationKey, PendingAnswer, scope_of
from backend.practice.domain.paper import Paper

_STEM = "计算：(-3)+5"


class _Log:
    def __init__(self) -> None:
        self.events: list[object] = []

    def log(self, event: object) -> None:
        self.events.append(event)


class CatalogPracticeCases:
    approvals: object
    practice: object
    files: object

    def test_snapshot_round_trip(self) -> None:
        stored = _snapshot()
        self.approvals.put(stored)  # type: ignore[attr-defined]
        self.assertEqual(self.approvals.read_snapshot(stored.question_version_id), stored)  # type: ignore[attr-defined]
        changed = replace(stored, stem="改后的题干", question_approved=True)
        self.approvals.put(changed)  # type: ignore[attr-defined]
        self.assertEqual(self.approvals.read_snapshot(stored.question_version_id), changed)  # type: ignore[attr-defined]

    def test_insert_if_absent_keeps_the_first_answer_id(self) -> None:
        first = _snapshot()
        self.assertTrue(self.approvals.insert_if_absent(first))  # type: ignore[attr-defined]
        second = replace(first, question_version_id="q-c1-b", stem="另一题")
        self.assertFalse(self.approvals.insert_if_absent(second))  # type: ignore[attr-defined]
        self.assertIsNone(self.approvals.read_snapshot("q-c1-b"))  # type: ignore[attr-defined]
        self.assertEqual(self.approvals.read_snapshot(first.question_version_id), first)  # type: ignore[attr-defined]
        self.assertTrue(self.approvals.has_version_id(first.answer_version_id))  # type: ignore[attr-defined]
        self.assertFalse(self.approvals.has_version_id("missing-version"))  # type: ignore[attr-defined]

    def test_replace_if_current_rejects_a_stale_snapshot(self) -> None:
        current = _snapshot()
        self.approvals.put(current)  # type: ignore[attr-defined]
        updated = replace(current, stem="新题干", question_approved=True)
        self.assertTrue(self.approvals.replace_if_current(current, updated))  # type: ignore[attr-defined]
        self.assertFalse(self.approvals.replace_if_current(current, replace(updated, stem="过期")))  # type: ignore[attr-defined]
        self.assertEqual(self.approvals.read_snapshot(current.question_version_id), updated)  # type: ignore[attr-defined]
        self.assertFalse(self.approvals.replace_if_current(updated, replace(updated, question_version_id="other")))  # type: ignore[attr-defined]

    def test_missing_snapshot_is_snapshot_not_found(self) -> None:
        with self.assertRaises(StoreFault) as caught:  # type: ignore[attr-defined]
            self.approvals.require_snapshot("missing")  # type: ignore[attr-defined]
        self.assertEqual(caught.exception.code, "snapshot_not_found")  # type: ignore[attr-defined]

    def test_issue_round_trip_keeps_null_file_fields(self) -> None:
        paper = _paper()
        answer = _answer(paper)
        self.practice.place_issued(paper, answer)  # type: ignore[attr-defined]
        self.assertEqual(self.practice.get_paper(paper.paper_id), paper)  # type: ignore[attr-defined]
        self.assertIsNone(paper.file_id)
        self.assertIsNone(paper.file_checksum)
        self.assertEqual(self.practice.find_answer_for_review(paper.paper_id, "sq-1", paper.review_version_id), answer)  # type: ignore[attr-defined]
        self.assertEqual(self.practice.list_papers(), (paper,))  # type: ignore[attr-defined]
        self.assertEqual(self.practice.paper_count(), 1)  # type: ignore[attr-defined]

    def test_incomplete_issue_writes_nothing(self) -> None:
        paper = _paper()
        answer = replace(_answer(paper), paper_id="other-paper")
        with self.assertRaises(ValueError):  # type: ignore[attr-defined]
            self.practice.place_issued(paper, answer)  # type: ignore[attr-defined]
        self.assertEqual(self.practice.paper_count(), 0)  # type: ignore[attr-defined]

    def test_missing_paper_is_paper_not_found(self) -> None:
        with self.assertRaises(StoreFault) as caught:  # type: ignore[attr-defined]
            self.practice.require_paper("missing")  # type: ignore[attr-defined]
        self.assertEqual(caught.exception.code, "paper_not_found")  # type: ignore[attr-defined]
        with self.assertRaises(StoreFault) as caught:  # type: ignore[attr-defined]
            self.practice.set_review_version("missing", "rev-2")  # type: ignore[attr-defined]
        self.assertEqual(caught.exception.code, "paper_not_found")  # type: ignore[attr-defined]
        with self.assertRaises(StoreFault) as caught:  # type: ignore[attr-defined]
            self.practice.replace_paper(_paper())  # type: ignore[attr-defined]
        self.assertEqual(caught.exception.code, "paper_not_found")  # type: ignore[attr-defined]

    def test_commit_then_read_confirmation(self) -> None:
        paper = _paper()
        self.practice.place_issued(paper, _answer(paper))  # type: ignore[attr-defined]
        record = _confirmation(paper, "conf-c1", "op-c1")
        placed = self.practice.commit_confirmation(record)  # type: ignore[attr-defined]
        self.assertEqual(placed, record)
        self.assertEqual(self.practice.get_confirmation(scope_of(record)), record)  # type: ignore[attr-defined]
        self.assertEqual(self.practice.find_slot(paper.paper_id, "sq-1", paper.review_version_id), scope_of(record))  # type: ignore[attr-defined]
        self.assertEqual(self.practice.confirmation_count(), 1)  # type: ignore[attr-defined]
        self.assertEqual(self.practice.list_confirmations(), (record,))  # type: ignore[attr-defined]

    def test_taken_slot_commit_is_confirm_conflict(self) -> None:
        paper = _paper()
        self.practice.place_issued(paper, _answer(paper))  # type: ignore[attr-defined]
        first = _confirmation(paper, "conf-c1", "op-c1")
        self.assertEqual(self.practice.commit_confirmation(first), first)  # type: ignore[attr-defined]
        second = _confirmation(paper, "conf-c1-b", "op-c1-b")
        refused = self.practice.commit_confirmation(second)  # type: ignore[attr-defined]
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.code, "confirm_conflict")  # type: ignore[attr-defined]
        self.assertEqual(self.practice.confirmation_count(), 1)  # type: ignore[attr-defined]

    def test_insert_on_taken_slot_is_slot_conflict(self) -> None:
        paper = _paper()
        self.practice.add_paper(paper)  # type: ignore[attr-defined]
        first = _confirmation(paper, "conf-c1", "op-c1")
        self.practice.insert_confirmation(first)  # type: ignore[attr-defined]
        second = _confirmation(paper, "conf-c1-b", "op-c1-b")
        with self.assertRaises(StoreFault) as caught:  # type: ignore[attr-defined]
            self.practice.insert_confirmation(second)  # type: ignore[attr-defined]
        self.assertEqual(caught.exception.code, "slot_conflict")  # type: ignore[attr-defined]
        self.assertEqual(self.practice.get_confirmation(scope_of(first)), first)  # type: ignore[attr-defined]

    def test_file_round_trip_and_missing(self) -> None:
        payload = "学生写下了 5".encode()
        file_id, checksum = self.files.add(payload)  # type: ignore[attr-defined]
        self.assertEqual(self.files.read(file_id), payload)  # type: ignore[attr-defined]
        self.assertEqual(self.files.require(file_id), payload)  # type: ignore[attr-defined]
        self.assertEqual(file_id, "file-" + checksum[:16])
        with self.assertRaises(StoreFault) as caught:  # type: ignore[attr-defined]
            self.files.require("file-0123456789abcdef")  # type: ignore[attr-defined]
        self.assertEqual(caught.exception.code, "file_missing")  # type: ignore[attr-defined]
        self.assertIsNone(self.files.read("not-a-file"))  # type: ignore[attr-defined]

    def test_store_fault_keeps_its_code(self) -> None:
        logger = _Log()

        def raise_fault() -> None:
            raise StoreFault("file_missing")

        result = read_store(raise_fault, logger, "req-c1", "practice.files", time.perf_counter())  # type: ignore[arg-type]
        self.assertIsInstance(result, Err)
        self.assertEqual(result.code, "file_missing")  # type: ignore[attr-defined]
        self.assertEqual(logger.events, [])


class MemoryContractTest(CatalogPracticeCases, unittest.TestCase):
    def setUp(self) -> None:
        self.approvals = MemoryApprovals()
        self.practice = MemoryPractice()
        self.files = MemoryFiles()


class PgContractTest(CatalogPracticeCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_approvals import PgApprovals
        from backend.practice.adapters.pg_files import PgFiles
        from backend.practice.adapters.pg_practice import PgPractice

        self.pool = _pool()
        _truncate(self.pool)
        self._directory = tempfile.TemporaryDirectory()
        self.approvals = PgApprovals(self.pool)
        self.practice = PgPractice(self.pool)
        self.files = PgFiles(self.pool, Path(self._directory.name))

    def tearDown(self) -> None:
        directory = getattr(self, "_directory", None)
        if directory is not None:
            directory.cleanup()

    def test_paper_page_follows_the_paper(self) -> None:
        paper = _paper()
        self.practice.place_issued(paper, _answer(paper))  # type: ignore[attr-defined]
        self.assertEqual(_scalar(self.pool, "SELECT count(*) FROM paper_pages WHERE paper_id = %s", (paper.paper_id,)), 1)
        self.assertEqual(_scalar(self.pool, "SELECT page_number FROM paper_pages WHERE paper_id = %s", (paper.paper_id,)), 1)


def _snapshot() -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id="q-c1",
        answer_version_id="a-c1",
        asset_ids=("page-synth", "item-synth"),
        layout_template_id="layout-1",
        question_approved=False,
        answer_approved=False,
        retired=False,
        subject_id="math",
        item_order=("sq-1",),
        stem=_STEM,
        answer_text="2",
    )


def _paper() -> Paper:
    return Paper(
        paper_id="paper-c1",
        teacher_id="teacher-c1",
        student_id="student-c1",
        subject_id="math",
        question_version_id="q-c1",
        answer_version_id="a-c1",
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        review_version_id="rev-c1",
        file_id=None,
        status="待渲染",
        item_order=("sq-1",),
        file_checksum=None,
        formula="(-3)+5",
    )


def _answer(paper: Paper) -> PendingAnswer:
    return PendingAnswer(
        fixture_answer_id="ans-c1",
        paper_id=paper.paper_id,
        sub_question_id="sq-1",
        review_version_id=paper.review_version_id,
        student_id=paper.student_id,
        status="pending",
        answer_text="学生写下了 5",
    )


def _confirmation(paper: Paper, confirmation_id: str, operation_key: str) -> Confirmation:
    return Confirmation(
        confirmation_id=confirmation_id,
        operation_key=OperationKey(operation_key),
        paper_id=paper.paper_id,
        sub_question_id="sq-1",
        teacher_id=paper.teacher_id,
        review_version_id=paper.review_version_id,
        decision="adopt",
        fixture_answer_id="ans-c1",
    )


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


def _truncate(pool: object) -> None:
    statement = """
        TRUNCATE TABLE confirmations, attempts, paper_pages, papers, files, approvals
        RESTART IDENTITY CASCADE
    """
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement)


def _scalar(pool: object, statement: str, params: tuple[object, ...]) -> int:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            row = conn.execute(statement, params).fetchone()
    return int(row[0])


_POOL: object | None = None
