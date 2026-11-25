"""Current suggestion and one in-memory teacher conclusion."""

from __future__ import annotations

import unittest

from backend.ai.domain.current import PageStamp, select_recognition
from backend.ai.domain.records import Run, Suggestion
from backend.practice.adapters.memory_decision import MemoryDecisions
from backend.practice.domain.decision import TeacherDecision


class CurrentSuggestionTest(unittest.TestCase):
    def test_current_run_is_the_latest_success_on_the_live_photo(self) -> None:
        pages = (
            PageStamp("intake-live", 1, False),
            PageStamp("intake-dead", 2, True),
        )
        runs = (
            _run("run-early", "intake-live", "2026-11-25T00:00:00Z", "2026-11-25T00:01:00Z", 1, "incorrect", "mismatch"),
            _run("run-late", "intake-live", "2026-11-25T00:02:00Z", "2026-11-25T00:03:00Z", 1, "correct", "mismatch"),
            _run("run-fail", "intake-live", "2026-11-25T00:04:00Z", "2026-11-25T00:05:00Z", 1, "incorrect", status="failed"),
            _run("run-stale", "intake-dead", "2026-11-25T00:06:00Z", "2026-11-25T00:07:00Z", 2, "correct", "mismatch"),
        )
        found = select_recognition(pages, runs)
        by_order = {int(row["order_no"]): row for row in found["suggestions"]}  # type: ignore[index]
        self.assertEqual(set(by_order), {1})
        self.assertEqual(by_order[1]["run_id"], "run-late")
        self.assertEqual(by_order[1]["verdict"], "correct")
        self.assertEqual(found["stale_orders"], [2])
        self.assertEqual(found["mismatch_pages"], [1])
        self.assertEqual(found["received_pages"], [1])
        tied = select_recognition(
            (PageStamp("intake-tie", 1, False),),
            (
                _run("run-b", "intake-tie", "2026-11-25T00:00:00Z", "2026-11-25T00:03:00Z", 1, "incorrect"),
                _run("run-a", "intake-tie", "2026-11-25T00:02:00Z", "2026-11-25T00:03:00Z", 1, "partial"),
            ),
        )
        tied_row = tied["suggestions"][0]  # type: ignore[index]
        self.assertEqual(tied_row["run_id"], "run-a")


class MemoryDecisionTest(unittest.TestCase):
    def test_memory_one_current_row(self) -> None:
        store = MemoryDecisions()
        store.replace(_decision("decision-r7-a", "2026-11-25T00:00:00Z", "correct"))
        store.replace(_decision("decision-r7-b", "2026-11-25T00:01:00Z", "incorrect"))
        current = store.current("paper-r7", 1)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.decision_id, "decision-r7-b")
        self.assertEqual(current.verdict, "incorrect")
        self.assertEqual(len(store.currents("paper-r7")), 1)
        history = store.history("paper-r7")
        self.assertEqual([row.decision_id for row in history], ["decision-r7-a", "decision-r7-b"])
        self.assertEqual(history[0].voided_at, "2026-11-25T00:01:00Z")
        self.assertEqual(history[1].voided_at, "")


def _run(
    run_id: str,
    intake_id: str,
    started: str,
    finished: str,
    order_no: int,
    verdict: str,
    external: str = "unread",
    status: str = "succeeded",
) -> Run:
    return Run(
        run_id=run_id,
        intake_id=intake_id,
        provider="mock",
        model="mock",
        prompt_version="transcribe-v1/judge-v1",
        status=status,
        started_at=started,
        finished_at=finished,
        external_match=external,
        page_match="unread",
        suggestions=(
            Suggestion(
                run_id=run_id,
                paper_id="paper-r7",
                order_no=order_no,
                transcription="2",
                unreadable=False,
                confidence=0.91,
                verdict=verdict,
                reason="与标准答案一致",
                judged_by="model",
            ),
        ),
    )


def _decision(decision_id: str, decided_at: str, verdict: str) -> TeacherDecision:
    return TeacherDecision(
        decision_id=decision_id,
        paper_id="paper-r7",
        order_no=1,
        verdict=verdict,
        source="manual",
        decided_by="teacher-synth",
        decided_at=decided_at,
    )
