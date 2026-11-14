"""Core tests for the synthetic issue and confirm loop. No network and no database."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from backend.bootstrap.stdout_log import StdoutLogger
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.read_snapshot import read_snapshot
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice
from backend.practice.api import ConfirmCommand, IssuePaperCommand
from backend.practice.application.confirm_attempt import confirm_attempt
from backend.practice.application.issue_paper import issue_paper


class ListLogger:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class BrokenStore:
    def get_paper(self, paper_id: str) -> None:
        raise RuntimeError("store unavailable")

    def get_confirmation(self, operation_key: str) -> None:
        raise RuntimeError("store unavailable")

    def find_slot(self, paper_id: str, sub_question_id: str, review_version_id: str) -> None:
        raise RuntimeError("store unavailable")

    def add_confirmation(self, record: object) -> None:
        raise RuntimeError("store unavailable")

    def add_paper(self, paper: object) -> None:
        raise RuntimeError("store unavailable")


def approved() -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id="q-v1",
        answer_version_id="a-v1",
        asset_ids=("page-synth", "item-synth"),
        layout_template_id="layout-1",
        question_approved=True,
        answer_approved=True,
        retired=False,
    )


def issue_command() -> IssuePaperCommand:
    return IssuePaperCommand(
        teacher_id="teacher-synth",
        student_id="student-synth",
        subject_id="math",
        question_version_id="q-v1",
        review_version_id="rev-1",
    )


class CoreLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.approvals = MemoryApprovals()
        self.practice = MemoryPractice()
        self.auth = MemoryAuth()
        self.logger = ListLogger()
        self.auth.grant("teacher-synth", "student-synth", "math")
        self.ids = iter(["paper-1", "conf-1", "conf-2", "conf-3"])

    def next_id(self) -> str:
        return next(self.ids)

    def test_unapproved_issue_is_refused_and_writes_nothing(self) -> None:
        self.approvals.put(
            ApprovalSnapshot(
                question_version_id="q-v1",
                answer_version_id="a-v1",
                asset_ids=("page-synth",),
                layout_template_id="layout-1",
                question_approved=False,
                answer_approved=True,
                retired=False,
            )
        )
        result = issue_paper(
            issue_command(),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-refuse",
            self.next_id,
        )
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "not_approved")
        self.assertEqual(self.practice.paper_count(), 0)
        refused = [event for event in self.logger.events if event.event == "use_case_refused"]
        self.assertEqual(refused[0].request_id, "req-refuse")
        self.assertEqual(refused[0].level, "WARN")

    def test_confirm_creates_one_official_record(self) -> None:
        paper = self._issue()
        suggestion = "fake-adapter-output"
        result = self._confirm(paper.paper_id, "key-1", "adopt")
        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertEqual(result.value.decision, "adopt")
        self.assertNotEqual(result.value.decision, suggestion)
        self.assertEqual(self.practice.confirmation_count(), 1)
        self.assertEqual(result.value.fixture_answer_id, "fixture-answer-1")

    def test_same_key_replay_returns_the_original(self) -> None:
        paper = self._issue()
        first = self._confirm(paper.paper_id, "key-1", "adopt")
        second = self._confirm(paper.paper_id, "key-1", "adopt")
        assert isinstance(first, Ok)
        assert isinstance(second, Ok)
        self.assertIs(second.value, first.value)
        self.assertEqual(second.value.confirmation_id, first.value.confirmation_id)
        self.assertEqual(second.value.decision, "adopt")
        self.assertEqual(self.practice.confirmation_count(), 1)

    def test_same_key_different_content_is_refused(self) -> None:
        paper = self._issue()
        self._confirm(paper.paper_id, "key-1", "adopt")
        again = self._confirm(paper.paper_id, "key-1", "reject")
        self.assertIsInstance(again, Err)
        assert isinstance(again, Err)
        self.assertEqual(again.code, "key_content_mismatch")
        self.assertEqual(self.practice.confirmation_count(), 1)
        stored = self.practice.get_confirmation("key-1")
        assert stored is not None
        self.assertEqual(stored.decision, "adopt")

    def test_issued_snapshot_stays_when_the_catalog_changes(self) -> None:
        paper = self._issue()
        self.approvals.put(
            ApprovalSnapshot(
                question_version_id="q-v1",
                answer_version_id="a-v2",
                asset_ids=("page-synth-new",),
                layout_template_id="layout-2",
                question_approved=True,
                answer_approved=True,
                retired=False,
            )
        )
        stored = self.practice.get_paper(paper.paper_id)
        assert stored is not None
        self.assertEqual(stored.question_version_id, "q-v1")
        self.assertEqual(stored.answer_version_id, "a-v1")
        self.assertEqual(stored.asset_ids, ("page-synth", "item-synth"))
        self.assertEqual(stored.layout_template_id, "layout-1")
        self.assertIsNone(stored.file_id)
        self.assertEqual(stored.status, "待渲染")

    def test_second_key_on_the_same_review_conflicts(self) -> None:
        paper = self._issue()
        first = self._confirm(paper.paper_id, "key-1", "adopt")
        second = self._confirm(paper.paper_id, "key-2", "adopt")
        self.assertIsInstance(first, Ok)
        self.assertIsInstance(second, Err)
        assert isinstance(second, Err)
        self.assertEqual(second.code, "confirm_conflict")
        self.assertEqual(self.practice.confirmation_count(), 1)

    def test_new_key_is_refused_when_the_review_version_changed(self) -> None:
        paper = self._issue()
        self.practice.set_review_version(paper.paper_id, "rev-2")
        refused = self._confirm(paper.paper_id, "key-new", "adopt")
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertEqual(refused.code, "version_mismatch")
        stored = self.practice.get_paper(paper.paper_id)
        assert stored is not None
        self.assertEqual(stored.question_version_id, "q-v1")
        self.assertEqual(self.practice.confirmation_count(), 0)

    def test_unauthorized_issue_writes_nothing(self) -> None:
        self.approvals.put(approved())
        command = IssuePaperCommand(
            teacher_id="teacher-other",
            student_id="student-synth",
            subject_id="math",
            question_version_id="q-v1",
            review_version_id="rev-1",
        )
        result = issue_paper(
            command,
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-auth",
            self.next_id,
        )
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "unauthorized")
        self.assertEqual(self.practice.paper_count(), 0)

    def test_blank_operation_key_writes_nothing(self) -> None:
        paper = self._issue()
        result = self._confirm(paper.paper_id, "   ", "adopt")
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "empty_operation_key")
        self.assertEqual(self.practice.confirmation_count(), 0)

    def test_blank_version_id_is_not_frozen(self) -> None:
        self.approvals.put(
            ApprovalSnapshot(
                question_version_id="  ",
                answer_version_id="a-v1",
                asset_ids=("page-synth",),
                layout_template_id="layout-1",
                question_approved=True,
                answer_approved=True,
                retired=False,
            )
        )
        result = issue_paper(
            IssuePaperCommand(
                teacher_id="teacher-synth",
                student_id="student-synth",
                subject_id="math",
                question_version_id="  ",
                review_version_id="rev-1",
            ),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-blank",
            self.next_id,
        )
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "not_frozen")
        self.assertEqual(self.practice.paper_count(), 0)

    def test_catalog_read_refuses_unapproved(self) -> None:
        self.approvals.put(
            ApprovalSnapshot(
                question_version_id="q-v1",
                answer_version_id="a-v1",
                asset_ids=("page-synth",),
                layout_template_id="layout-1",
                question_approved=True,
                answer_approved=False,
                retired=False,
            )
        )
        result = read_snapshot("q-v1", self.approvals, self.logger, "req-read")
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "not_approved")

    def test_store_failure_logs_error_with_request_id(self) -> None:
        logger = StdoutLogger()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = confirm_attempt(
                ConfirmCommand(
                    operation_key="key-1",
                    paper_id="paper-1",
                    sub_question_id="sq-1",
                    teacher_id="teacher-synth",
                    review_version_id="rev-1",
                    decision="adopt",
                    fixture_answer_id="fixture-answer-1",
                ),
                self.auth,
                BrokenStore(),
                logger,
                "req-err-1",
                self.next_id,
            )
        text = buffer.getvalue()
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "store_failed")
        self.assertIn("req-err-1", text)
        self.assertIn("ERROR", text)
        self.assertIn("use_case_failed", text)

    def _issue(self):
        self.approvals.put(approved())
        result = issue_paper(
            issue_command(),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-issue",
            self.next_id,
        )
        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        return result.value

    def _confirm(self, paper_id: str, operation_key: str, decision: str):
        return confirm_attempt(
            ConfirmCommand(
                operation_key=operation_key,
                paper_id=paper_id,
                sub_question_id="sq-1",
                teacher_id="teacher-synth",
                review_version_id="rev-1",
                decision=decision,
                fixture_answer_id="fixture-answer-1",
            ),
            self.auth,
            self.practice,
            self.logger,
            "req-confirm",
            self.next_id,
        )


if __name__ == "__main__":
    unittest.main()
