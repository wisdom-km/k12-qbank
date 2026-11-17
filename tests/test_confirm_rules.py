"""Concurrency, answer ownership, and trusted-subject regressions. Synthetic ids only."""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice
from backend.practice.api import ConfirmCommand, IssuePaperCommand
from backend.practice.application.confirm_attempt import confirm_attempt
from backend.practice.application.issue_paper import issue_paper
from backend.practice.domain.confirm import Confirmation, ConfirmationScope, OperationKey, PendingAnswer

ROOT = Path(__file__).resolve().parents[1]


class ListLogger:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class RaiseAfterWrite:
    """The success line fails. The degraded line is kept."""

    def __init__(self, event_name: str) -> None:
        self.event_name = event_name
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        if event.event == self.event_name:
            raise RuntimeError("sink down")
        self.events.append(event)


class IdFactory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._n = 0

    def __call__(self) -> str:
        with self._lock:
            self._n += 1
            return f"conf-{self._n}"


class GateStore(MemoryPractice):
    def __init__(self) -> None:
        super().__init__()
        self.gate: threading.Barrier | None = None
        self.release: threading.Event | None = None
        self.arrived: threading.Event | None = None

    def commit_confirmation(self, record: Confirmation) -> Confirmation | Err:
        if self.arrived is not None:
            self.arrived.set()
        if self.release is not None:
            self.release.wait(5)
        if self.gate is not None:
            self.gate.wait(5)
        return super().commit_confirmation(record)


def approved() -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id="q-v1",
        answer_version_id="a-v1",
        asset_ids=("page-synth", "item-synth"),
        layout_template_id="layout-1",
        question_approved=True,
        answer_approved=True,
        retired=False,
        subject_id="math",
        item_order=("sq-1",),
    )


class ConfirmRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.approvals = MemoryApprovals()
        self.practice = GateStore()
        self.auth = MemoryAuth()
        self.logger = ListLogger()
        self.auth.grant("teacher-synth", "student-synth", "math")
        self.ids = IdFactory()

    def test_concurrent_keys_leave_one_record(self) -> None:
        paper = self._issue()
        self.practice.gate = threading.Barrier(2)
        results: list[Ok[Confirmation] | Err] = []
        lock = threading.Lock()

        def run(key: str, teacher: str) -> None:
            outcome = self._confirm(paper.paper_id, key, "adopt", teacher=teacher)
            with lock:
                results.append(outcome)

        self.auth.grant("teacher-b", "student-synth", "math")
        first = threading.Thread(target=run, args=("key-1", "teacher-synth"))
        second = threading.Thread(target=run, args=("key-2", "teacher-b"))
        first.start()
        second.start()
        first.join(5)
        second.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        oks = [item for item in results if isinstance(item, Ok)]
        errs = [item for item in results if isinstance(item, Err)]
        self.assertEqual(len(oks), 1)
        self.assertEqual(len(errs), 1)
        assert isinstance(oks[0], Ok)
        assert isinstance(errs[0], Err)
        self.assertEqual(errs[0].code, "confirm_conflict")
        self.assertEqual(self.practice.confirmation_count(), 1)
        print(f"RACE different-keys id={oks[0].value.confirmation_id} count=1")

    def test_same_key_on_two_papers_writes_two_records(self) -> None:
        first = self._issue_answer("ans-a")
        second = self._issue_answer("ans-b")
        left = self._confirm(first.paper_id, "key-1", "adopt", fixture_answer_id="ans-a")
        right = self._confirm(second.paper_id, "key-1", "adopt", fixture_answer_id="ans-b")
        self.assertIsInstance(left, Ok)
        self.assertIsInstance(right, Ok)
        assert isinstance(left, Ok)
        assert isinstance(right, Ok)
        self.assertNotEqual(left.value.confirmation_id, right.value.confirmation_id)
        self.assertEqual(self.practice.confirmation_count(), 2)
        print(f"SCOPE two-papers ids={left.value.confirmation_id},{right.value.confirmation_id} count=2")

    def test_same_key_on_two_sub_questions_writes_two_records(self) -> None:
        paper = self._issue_answer("ans-a", "sq-1")
        self.practice.put_answer(
            PendingAnswer(
                fixture_answer_id="ans-b",
                paper_id=paper.paper_id,
                sub_question_id="sq-2",
                review_version_id="rev-1",
                student_id="student-synth",
                status="pending",
            )
        )
        left = self._confirm(paper.paper_id, "key-1", "adopt", fixture_answer_id="ans-a", sub_question_id="sq-1")
        right = self._confirm(paper.paper_id, "key-1", "adopt", fixture_answer_id="ans-b", sub_question_id="sq-2")
        self.assertIsInstance(left, Ok)
        self.assertIsInstance(right, Ok)
        assert isinstance(left, Ok)
        assert isinstance(right, Ok)
        self.assertNotEqual(left.value.confirmation_id, right.value.confirmation_id)
        self.assertEqual(self.practice.confirmation_count(), 2)
        print(f"SCOPE two-subs ids={left.value.confirmation_id},{right.value.confirmation_id} count=2")

    def test_two_teachers_same_key_string_conflict_on_one_slot(self) -> None:
        paper = self._issue()
        self.practice.gate = threading.Barrier(2)
        self.auth.grant("teacher-b", "student-synth", "math")
        results: list[Ok[Confirmation] | Err] = []
        lock = threading.Lock()

        def run(teacher: str) -> None:
            outcome = self._confirm(paper.paper_id, "key-1", "adopt", teacher=teacher)
            with lock:
                results.append(outcome)

        first = threading.Thread(target=run, args=("teacher-synth",))
        second = threading.Thread(target=run, args=("teacher-b",))
        first.start()
        second.start()
        first.join(5)
        second.join(5)
        oks = [item for item in results if isinstance(item, Ok)]
        errs = [item for item in results if isinstance(item, Err)]
        self.assertEqual(len(oks), 1)
        self.assertEqual(len(errs), 1)
        assert isinstance(oks[0], Ok)
        assert isinstance(errs[0], Err)
        self.assertEqual(errs[0].code, "confirm_conflict")
        self.assertEqual(self.practice.confirmation_count(), 1)
        print(f"SCOPE same-string-two-teachers id={oks[0].value.confirmation_id} count=1")

    def test_concurrent_same_key_returns_one_id(self) -> None:
        paper = self._issue()
        self.practice.gate = threading.Barrier(2)
        results: list[Ok[Confirmation] | Err] = []
        lock = threading.Lock()

        def run() -> None:
            outcome = self._confirm(paper.paper_id, "key-1", "adopt")
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(item, Ok) for item in results))
        assert isinstance(results[0], Ok)
        assert isinstance(results[1], Ok)
        self.assertEqual(results[0].value.confirmation_id, results[1].value.confirmation_id)
        self.assertEqual(self.practice.confirmation_count(), 1)
        print(f"RACE same-key id={results[0].value.confirmation_id} count=1")

    def test_concurrent_same_key_different_content_keeps_one(self) -> None:
        paper = self._issue()
        self.practice.gate = threading.Barrier(2)
        results: list[Ok[Confirmation] | Err] = []
        lock = threading.Lock()

        def run(decision: str) -> None:
            outcome = self._confirm(paper.paper_id, "key-1", decision)
            with lock:
                results.append(outcome)

        first = threading.Thread(target=run, args=("adopt",))
        second = threading.Thread(target=run, args=("reject",))
        first.start()
        second.start()
        first.join(5)
        second.join(5)
        oks = [item for item in results if isinstance(item, Ok)]
        errs = [item for item in results if isinstance(item, Err)]
        self.assertEqual(len(oks), 1)
        self.assertEqual(errs[0].code, "key_content_mismatch")
        assert isinstance(oks[0], Ok)
        stored = self.practice.get_confirmation(self._scope(paper.paper_id))
        assert stored is not None
        self.assertEqual(stored.confirmation_id, oks[0].value.confirmation_id)
        self.assertEqual(stored.decision, oks[0].value.decision)
        self.assertEqual(self.practice.confirmation_count(), 1)
        print(f"RACE mismatch id={oks[0].value.confirmation_id} decision={stored.decision} count=1")

    def test_version_update_beats_the_first_confirm(self) -> None:
        paper = self._issue()
        self.practice.arrived = threading.Event()
        self.practice.release = threading.Event()
        holder: dict[str, Ok[Confirmation] | Err] = {}

        def run() -> None:
            holder["result"] = self._confirm(paper.paper_id, "key-new", "adopt")

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(self.practice.arrived.wait(5))
        self.practice.set_review_version(paper.paper_id, "rev-2")
        self.practice.release.set()
        thread.join(5)
        result = holder["result"]
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "version_mismatch")
        self.assertEqual(self.practice.confirmation_count(), 0)
        print("RACE version-first id=none count=0")

    def test_replay_beats_a_later_version_update(self) -> None:
        paper = self._issue()
        first = self._confirm(paper.paper_id, "key-1", "adopt")
        assert isinstance(first, Ok)
        self.practice.arrived = threading.Event()
        self.practice.release = threading.Event()
        holder: dict[str, Ok[Confirmation] | Err] = {}

        def run() -> None:
            holder["result"] = self._confirm(paper.paper_id, "key-1", "adopt")

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(self.practice.arrived.wait(5))
        self.practice.set_review_version(paper.paper_id, "rev-2")
        self.practice.release.set()
        thread.join(5)
        replay = holder["result"]
        self.assertIsInstance(replay, Ok)
        assert isinstance(replay, Ok)
        self.assertEqual(replay.value.confirmation_id, first.value.confirmation_id)
        self.assertEqual(self.practice.confirmation_count(), 1)
        stored = self.practice.get_paper(paper.paper_id)
        assert stored is not None
        self.assertEqual(stored.review_version_id, "rev-2")
        kept = self.practice.get_confirmation(self._scope(paper.paper_id))
        assert kept is not None
        self.assertEqual(kept.decision, "adopt")
        print(f"RACE replay-during-version id={replay.value.confirmation_id} count=1")

    def test_cross_paper_answer_is_refused(self) -> None:
        first = self._issue()
        second = self._issue_without_answer()
        result = self._confirm(second.paper_id, "key-cross", "adopt")
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "answer_not_owned")
        self.assertEqual(self.practice.confirmation_count(), 0)
        self.assertEqual(self.practice.paper_count(), 2)
        self.assertIsNone(self.practice.get_confirmation(self._scope(second.paper_id, "key-cross")))
        self.assertNotEqual(first.paper_id, second.paper_id)

    def test_unknown_sub_question_and_answer_are_refused(self) -> None:
        paper = self._issue()
        unknown_sub = self._confirm(paper.paper_id, "key-sub", "adopt", sub_question_id="sq-missing")
        unknown_answer = self._confirm(paper.paper_id, "key-ans", "adopt", fixture_answer_id="missing-answer")
        self.assertIsInstance(unknown_sub, Err)
        self.assertIsInstance(unknown_answer, Err)
        assert isinstance(unknown_sub, Err)
        assert isinstance(unknown_answer, Err)
        self.assertEqual(unknown_sub.code, "answer_not_owned")
        self.assertEqual(unknown_answer.code, "answer_not_owned")
        self.assertEqual(self.practice.confirmation_count(), 0)

    def test_answer_not_pending_is_refused(self) -> None:
        paper = self._issue()
        self.practice.put_answer(
            PendingAnswer(
                fixture_answer_id="fixture-answer-1",
                paper_id=paper.paper_id,
                sub_question_id="sq-1",
                review_version_id="rev-1",
                student_id="student-synth",
                status="closed",
            )
        )
        result = self._confirm(paper.paper_id, "key-closed", "adopt")
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "answer_not_owned")
        self.assertEqual(self.practice.confirmation_count(), 0)

    def test_invalid_decision_keeps_the_existing_record(self) -> None:
        paper = self._issue()
        first = self._confirm(paper.paper_id, "key-1", "adopt")
        assert isinstance(first, Ok)
        refused = self._confirm(paper.paper_id, "key-1", "score-99")
        fresh = self._confirm(paper.paper_id, "key-new", "guess")
        self.assertIsInstance(refused, Err)
        self.assertIsInstance(fresh, Err)
        assert isinstance(refused, Err)
        assert isinstance(fresh, Err)
        self.assertEqual(refused.code, "invalid_decision")
        self.assertEqual(fresh.code, "invalid_decision")
        self.assertEqual(self.practice.confirmation_count(), 1)
        stored = self.practice.get_confirmation(self._scope(paper.paper_id))
        assert stored is not None
        self.assertEqual(stored.confirmation_id, first.value.confirmation_id)
        self.assertEqual(stored.decision, "adopt")

    def test_unauthorized_replay_does_not_return_the_original(self) -> None:
        paper = self._issue()
        first = self._confirm(paper.paper_id, "key-1", "adopt")
        assert isinstance(first, Ok)
        replay = self._confirm(paper.paper_id, "key-1", "adopt", teacher="teacher-other")
        self.assertIsInstance(replay, Err)
        assert isinstance(replay, Err)
        self.assertEqual(replay.code, "unauthorized")
        self.assertEqual(self.practice.confirmation_count(), 1)
        stored = self.practice.get_confirmation(self._scope(paper.paper_id))
        assert stored is not None
        self.assertEqual(stored.confirmation_id, first.value.confirmation_id)

    def test_subject_mismatch_and_actor_mismatch_write_nothing(self) -> None:
        self.approvals.put(approved())
        self.auth.grant("teacher-other", "student-synth", "math")
        mismatch = issue_paper(
            IssuePaperCommand("teacher-synth", "student-synth", "english", "q-v1", "rev-1"),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-subject",
            self.ids,
            actor_teacher_id="teacher-synth",
        )
        actor = issue_paper(
            IssuePaperCommand("teacher-other", "student-synth", "math", "q-v1", "rev-1"),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-actor",
            self.ids,
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(mismatch, Err)
        self.assertIsInstance(actor, Err)
        assert isinstance(mismatch, Err)
        assert isinstance(actor, Err)
        self.assertEqual(mismatch.code, "subject_mismatch")
        self.assertEqual(actor.code, "unauthorized")
        self.assertEqual(self.practice.paper_count(), 0)
        self.assertEqual(self.practice.confirmation_count(), 0)

    def test_retired_issue_writes_nothing(self) -> None:
        self.approvals.put(
            ApprovalSnapshot(
                question_version_id="q-v1",
                answer_version_id="a-v1",
                asset_ids=("page-synth",),
                layout_template_id="layout-1",
                question_approved=True,
                answer_approved=True,
                retired=True,
                subject_id="math",
            )
        )
        result = issue_paper(
            IssuePaperCommand("teacher-synth", "student-synth", "math", "q-v1", "rev-1"),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-retired",
            self.ids,
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertEqual(result.code, "retired")
        self.assertEqual(self.practice.paper_count(), 0)

    def test_log_failure_does_not_undo_the_write(self) -> None:
        self.approvals.put(approved())
        logger = RaiseAfterWrite("paper_created")
        result = issue_paper(
            IssuePaperCommand("teacher-synth", "student-synth", "math", "q-v1", "rev-1"),
            self.approvals,
            self.auth,
            self.practice,
            logger,
            "req-log",
            self.ids,
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(result, Ok)
        self.assertEqual(self.practice.paper_count(), 1)
        self.assertEqual(logger.events[0].event, "log_failed")
        self.assertEqual(logger.events[0].request_id, "req-log")
        self.assertEqual(logger.events[0].outcome, "log_degraded")
        self.assertNotIn("student", "".join(logger.events[0].fields().keys()))

    def _scope(self, paper_id: str, key: str = "key-1", teacher: str = "teacher-synth", sub: str = "sq-1") -> ConfirmationScope:
        return ConfirmationScope(paper_id, sub, teacher, OperationKey(key))

    def _issue(self):
        paper = self._issue_without_answer()
        raw = json.loads((ROOT / "docs" / "fixtures" / "rational-number-min.json").read_text(encoding="utf-8"))
        answer = raw["pending_answer"]
        self.practice.put_answer(
            PendingAnswer(
                fixture_answer_id=answer["fixture_answer_id"],
                paper_id=paper.paper_id,
                sub_question_id=answer["sub_question_id"],
                review_version_id=answer["review_version_id"],
                student_id=answer["student_id"],
                status=answer["status"],
            )
        )
        return paper

    def _issue_answer(self, answer_id: str, sub_question_id: str = "sq-1"):
        paper = self._issue_without_answer()
        self.practice.put_answer(
            PendingAnswer(
                fixture_answer_id=answer_id,
                paper_id=paper.paper_id,
                sub_question_id=sub_question_id,
                review_version_id="rev-1",
                student_id="student-synth",
                status="pending",
            )
        )
        return paper

    def _issue_without_answer(self):
        self.approvals.put(approved())
        result = issue_paper(
            IssuePaperCommand("teacher-synth", "student-synth", "math", "q-v1", "rev-1"),
            self.approvals,
            self.auth,
            self.practice,
            self.logger,
            "req-issue",
            self.ids,
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        return result.value

    def _confirm(
        self,
        paper_id: str,
        operation_key: str,
        decision: str,
        *,
        teacher: str = "teacher-synth",
        sub_question_id: str = "sq-1",
        fixture_answer_id: str = "fixture-answer-1",
    ):
        return confirm_attempt(
            ConfirmCommand(
                operation_key=operation_key,
                paper_id=paper_id,
                sub_question_id=sub_question_id,
                teacher_id=teacher,
                review_version_id="rev-1",
                decision=decision,
                fixture_answer_id=fixture_answer_id,
            ),
            self.auth,
            self.practice,
            self.logger,
            "req-confirm",
            self.ids,
            actor_teacher_id=teacher,
        )


if __name__ == "__main__":
    unittest.main()
