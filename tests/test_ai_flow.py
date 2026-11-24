"""Two-step recognition on the mock. Suggestions stay out of the run's raw reading."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from backend.ai.adapters.memory_runs import MemoryRuns
from backend.ai.adapters.mock_model import MockModel
from backend.ai.application.recognize import captured_judge, captured_transcribe, perform
from backend.ai.domain.records import Context, Run, WorkItem
from backend.bootstrap.http_app import create_app
from backend.bootstrap.compose import compose
from dataclasses import replace


class _Silent:
    def log(self, event: object) -> None:
        return


def _run(run_id: str, status: str = "queued") -> Run:
    return Run(
        run_id=run_id,
        intake_id="intake-flow",
        provider="mock",
        model="mock",
        prompt_version="transcribe-v1/judge-v1",
        status=status,
        started_at="2026-11-24T00:00:00Z",
    )


def _context(run_id: str, external: str) -> Context:
    return Context(
        run_id=run_id,
        intake_id="intake-flow",
        paper_id="paper-hidden-r6",
        page_no=1,
        image=b"\xff\xd8image-bytes-synth\xff\xd9",
        items=(
            WorkItem(1, "single_choice", "stem-choice-bait", "A", ((10.0, 10.0, 40.0, 20.0),), 0),
            WorkItem(2, "solution", "stem-solution-bait", "2", ((10.0, 100.0, 80.0, 40.0),), 0),
        ),
        expected_external_id=external,
        provider="mock",
        model_name="mock",
        prompt_version="transcribe-v1/judge-v1",
    )


class FlowTest(unittest.TestCase):
    def test_local_choice_and_model_solution(self) -> None:
        runs = MemoryRuns()
        runs.insert(_run("run-flow"))
        model = MockModel(transcription="A")
        perform(_context("run-flow", ""), model, runs, _Silent(), "req-flow")
        saved = runs.get("run-flow")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.status, "succeeded")
        by_order = {item.order_no: item for item in saved.suggestions}
        self.assertEqual(by_order[1].judged_by, "local")
        self.assertEqual(by_order[1].verdict, "correct")
        self.assertEqual(by_order[2].judged_by, "model")
        self.assertEqual(by_order[2].verdict, "correct")
        self.assertEqual(len(model.judge_asks), 1)
        self.assertEqual(model.judge_asks[0][0].order_no, 2)

    def test_transcribe_payload_has_no_stem_or_answer(self) -> None:
        runs = MemoryRuns()
        runs.insert(_run("run-redact"))
        model = MockModel(transcription="A", seen_external_id="synth-bait-ext")
        perform(_context("run-redact", "synth-bait-ext"), model, runs, _Silent(), "req-redact")
        text = json.dumps(captured_transcribe(model.transcribe_asks[0]), ensure_ascii=False)
        self.assertNotIn("stem-choice-bait", text)
        self.assertNotIn("stem-solution-bait", text)
        self.assertNotIn("standard_answer", text)
        self.assertNotIn("synth-bait-ext", text)
        self.assertNotIn("paper-hidden-r6", text)
        self.assertNotIn("student-hidden-r6", text)
        self.assertNotIn("name-bait-r6", text)
        judged = json.dumps(captured_judge(model.judge_asks[0]), ensure_ascii=False)
        self.assertIn("stem-solution-bait", judged)
        self.assertNotIn("stem-choice-bait", judged)
        self.assertNotIn("synth-bait-ext", judged)
        self.assertNotIn("paper-hidden-r6", judged)
        self.assertNotIn("student-hidden-r6", judged)
        self.assertNotIn("name-bait-r6", judged)
        self.assertNotIn("image-bytes-synth", text)
        self.assertNotIn("image-bytes-synth", judged)

    def test_external_match_consistent_mismatch_and_unread(self) -> None:
        cases = (
            ("run-same", "synth-bait-ext", "synth-bait-ext", "consistent"),
            ("run-diff", "synth-bait-ext", "synth-other-ext", "mismatch"),
            ("run-none", "synth-bait-ext", None, "unread"),
        )
        runs = MemoryRuns()
        for run_id, expected, seen, match in cases:
            runs.insert(_run(run_id))
            model = MockModel(transcription="A", seen_external_id=seen)
            perform(_context(run_id, expected), model, runs, _Silent(), run_id)
            saved = runs.get(run_id)
            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.external_match, match)
        dumped = runs.dump_text()
        self.assertNotIn("synth-bait-ext", dumped)
        self.assertNotIn("synth-other-ext", dumped)

    def test_invalid_judge_saves_no_suggestions(self) -> None:
        runs = MemoryRuns()
        runs.insert(_run("run-bad"))
        perform(_context("run-bad", ""), MockModel(transcription="A", scenario="invalid_judge"), runs, _Silent(), "req-bad")
        saved = runs.get("run-bad")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.status, "failed")
        self.assertEqual(saved.error_code, "model_output_invalid")
        self.assertEqual(saved.suggestions, ())

    def test_timeout_auth_and_invalid_fail_the_run(self) -> None:
        for scenario, code in (("timeout", "timeout"), ("auth", "auth_failed"), ("invalid", "model_output_invalid")):
            runs = MemoryRuns()
            run_id = "run-" + scenario
            runs.insert(_run(run_id))
            perform(_context(run_id, ""), MockModel(scenario=scenario), runs, _Silent(), run_id)
            saved = runs.get(run_id)
            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.status, "failed")
            self.assertEqual(saved.error_code, code)
            self.assertEqual(saved.suggestions, ())

    def test_startup_marks_running_interrupted(self) -> None:
        runs = MemoryRuns()
        runs.insert(_run("run-open", "running"))
        env = {"K12_ENV": "development", "K12_AI_PROVIDER": "mock", "K12_PG_DSN": "", "K12_LOG_FILE": "0"}
        with mock.patch.dict(os.environ, env, clear=False):
            wired = replace(compose(), ai_runs=runs)
            create_app(wired, seed=False)
        saved = runs.get("run-open")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.status, "failed")
        self.assertEqual(saved.error_code, "interrupted")
