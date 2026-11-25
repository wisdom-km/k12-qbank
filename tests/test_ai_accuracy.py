"""Accuracy counts stay on synthetic rows. No model call."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.ai.adapters.memory_runs import MemoryRuns
from backend.ai.application.accuracy import accuracy_report
from backend.ai.domain.accuracy import measure
from backend.ai.domain.records import Run, Suggestion
from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.practice.adapters.memory_decision import MemoryDecisions
from backend.practice.api import current_review_threshold
from backend.practice.domain.decision import TeacherDecision, review_threshold

PAPER = "paper-synth-acc"
INTAKE = "intake-synth-acc"
BAIT_TRANSCRIPTION = "synth-transcribe-secret"
BAIT_COMMENT = "synth-comment-secret"
BAIT_CORRECTED = "synth-corrected-secret"
BAIT_STUDENT = "synth-student-hidden"


class AccuracyMemoryTest(unittest.TestCase):
    def test_empty_store_does_not_divide_by_zero(self) -> None:
        report = accuracy_report(MemoryRuns(), MemoryDecisions())
        self.assertEqual(report["current_threshold"], 0.6)
        self.assertEqual(report["available_models"], [])
        self.assertEqual(report["runs"]["total"], 0)
        self.assertEqual(report["runs"]["external_match"], {"matched": 0, "mismatched": 0, "missing": 0})
        self.assertEqual(report["items"]["decided_total"], 0)
        self.assertIsNone(report["items"]["agreement_rate"])
        self.assertEqual([row["threshold"] for row in report["thresholds"]], [0.5, 0.6, 0.7, 0.8, 0.9])
        self.assertTrue(all(row["coverage_rate"] is None for row in report["thresholds"]))
        self.assertTrue(all(row["confident_accuracy"] is None for row in report["thresholds"]))

    def test_custom_threshold_joins_the_sweep(self) -> None:
        report = measure((), (), provider="", model="", current_threshold=0.65)
        self.assertEqual([row["threshold"] for row in report["thresholds"]], [0.5, 0.6, 0.65, 0.7, 0.8, 0.9])

    def test_env_cutoff_matches_the_grading_helper(self) -> None:
        for raw in ("", "0.6", "0.65", "nope", "2", "-0.1"):
            with mock.patch.dict(os.environ, {"K12_AI_REVIEW_THRESHOLD": raw}):
                self.assertEqual(current_review_threshold(), review_threshold(raw))
        with mock.patch.dict(os.environ, {"K12_AI_REVIEW_THRESHOLD": "0.65"}):
            report = accuracy_report(MemoryRuns(), MemoryDecisions())
        self.assertEqual(report["current_threshold"], 0.65)

    def test_one_confident_disagreement_drops_out_at_0_9(self) -> None:
        runs, decisions = _stores()
        _plant(runs, decisions, [_finished(_false_run())], [], [_voided_false(), _false_decision()])
        report = accuracy_report(runs, decisions)
        by_threshold = {row["threshold"]: row for row in report["thresholds"]}
        self.assertEqual(by_threshold[0.6]["false_confident"], 1)
        self.assertEqual(by_threshold[0.8]["false_confident"], 1)
        self.assertEqual(by_threshold[0.8]["confident_count"], 1)
        self.assertEqual(by_threshold[0.9]["false_confident"], 0)
        self.assertEqual(by_threshold[0.9]["review_needed_count"], 1)
        self.assertEqual(by_threshold[0.9]["confident_count"], 0)
        self.assertIsNone(by_threshold[0.9]["confident_accuracy"])
        self.assertEqual(report["items"]["disagreed"], 1)
        self.assertNotIn("decision-synth-void-false", [row.decision_id for row in decisions.all_current()])

    def test_mixed_rows_filter_by_model_and_skip_voided(self) -> None:
        runs, decisions = _stores()
        _plant(runs, decisions, _mixed_finished(), [_queued()], _mixed_decisions())
        report = accuracy_report(runs, decisions)
        _assert_mixed(self, report)
        self.assertEqual(
            [row.run_id for row in runs.all_runs()],
            ["run-synth-a", "run-synth-b", "run-synth-c", "run-synth-d"],
        )
        self.assertEqual(len(runs.all_runs()[0].suggestions), 5)
        self.assertNotIn("decision-synth-void", [row.decision_id for row in decisions.all_current()])
        narrowed = accuracy_report(runs, decisions, model="synth-model-b")
        self.assertEqual(narrowed["runs"]["total"], 1)
        self.assertEqual(narrowed["runs"]["failed"], 1)
        self.assertEqual(narrowed["runs"]["failed_by_code"], {"timeout": 1})
        self.assertEqual(narrowed["runs"]["input_tokens"], 5)
        self.assertEqual(narrowed["runs"]["output_tokens"], 1)
        self.assertEqual(narrowed["items"]["linked_ai"], 0)
        self.assertEqual(narrowed["items"]["unlinked_manual"], 2)
        self.assertEqual(narrowed["items"]["decided_total"], 2)
        other = accuracy_report(runs, decisions, provider="synth-other")
        self.assertEqual(other["runs"]["total"], 0)
        self.assertEqual(other["items"]["decided_total"], 1)
        self.assertEqual(other["items"]["unlinked_manual"], 1)
        padded = accuracy_report(runs, decisions, provider=" synth-prov ", model=" synth-model-a ")
        self.assertEqual(padded["runs"]["total"], 3)
        self.assertEqual(padded["items"]["linked_ai"], 6)


class AccuracyHttpTest(unittest.TestCase):
    def test_anonymous_is_401_and_teacher_is_403(self) -> None:
        app = _app()
        with TestClient(app) as client:
            anonymous = client.get("/api/admin/ai/accuracy")
            token = _login(client, ACTOR_TEACHER_ID)
            refused = client.get("/api/admin/ai/accuracy", headers={"X-K12-CSRF": token})
        self.assertEqual(anonymous.status_code, 401, anonymous.text)
        self.assertEqual(anonymous.json()["code"], "unauthenticated")
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["code"], "permission_denied")

    def test_admin_counts_hide_student_text_and_skip_audit(self) -> None:
        app = _app()
        with TestClient(app) as client:
            _login(client, ACTOR_ADMIN_ID)
            _plant(
                app.state.loop.ai_runs,
                app.state.loop.decisions,
                [_finished(_false_run())],
                [],
                [_false_decision(comment=BAIT_COMMENT + " " + BAIT_STUDENT, corrected=BAIT_CORRECTED)],
            )
            before = len(app.state.loop.identity.audits.rows)
            response = client.get("/api/admin/ai/accuracy")
            after = len(app.state.loop.identity.audits.rows)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["items"]["disagreed"], 1)
        self.assertEqual(body["runs"]["external_match"]["matched"], 1)
        self.assertEqual(after, before)
        for hidden in (BAIT_TRANSCRIPTION, BAIT_COMMENT, BAIT_CORRECTED, BAIT_STUDENT):
            self.assertNotIn(hidden, response.text)


def _assert_mixed(test: unittest.TestCase, report: dict[str, object]) -> None:
    runs = report["runs"]
    items = report["items"]
    assert isinstance(runs, dict)
    assert isinstance(items, dict)
    test.assertEqual(runs["total"], 4)
    test.assertEqual(runs["succeeded"], 2)
    test.assertEqual(runs["failed"], 1)
    test.assertEqual(runs["active"], 1)
    test.assertEqual(runs["failed_by_code"], {"timeout": 1})
    test.assertEqual(runs["external_match"], {"matched": 1, "mismatched": 1, "missing": 0})
    test.assertEqual(runs["page_match"], {"matched": 0, "mismatched": 1, "missing": 1})
    test.assertEqual(runs["input_tokens"], 20)
    test.assertEqual(runs["output_tokens"], 7)
    test.assertEqual(items["decided_total"], 8)
    test.assertEqual(items["linked_ai"], 6)
    test.assertEqual(items["unlinked_manual"], 2)
    test.assertEqual(items["by_source"], {"adopted": 1, "revised": 5, "manual": 0})
    test.assertEqual(items["ai_decisive"], 3)
    test.assertEqual(items["ai_unsure_or_unreadable"], 2)
    test.assertEqual(items["agreed"], 1)
    test.assertEqual(items["disagreed"], 2)
    test.assertEqual(items["agreement_rate"], 0.3333)
    judged = items["by_judged_by"]
    assert isinstance(judged, dict)
    test.assertEqual(judged["local"]["total"], 3)
    test.assertEqual(judged["local"]["decisive"], 1)
    test.assertEqual(judged["local"]["agreed"], 1)
    test.assertEqual(judged["local"]["unsure_or_unreadable"], 1)
    test.assertEqual(judged["local"]["agreement_rate"], 1.0)
    test.assertEqual(judged["model"]["total"], 3)
    test.assertEqual(judged["model"]["decisive"], 2)
    test.assertEqual(judged["model"]["disagreed"], 2)
    test.assertEqual(judged["model"]["unsure_or_unreadable"], 1)
    test.assertEqual(judged["model"]["agreement_rate"], 0.0)
    by_threshold = {row["threshold"]: row for row in report["thresholds"]}
    test.assertEqual(by_threshold[0.5]["confident_count"], 3)
    test.assertEqual(by_threshold[0.5]["false_confident"], 2)
    test.assertEqual(by_threshold[0.5]["coverage_rate"], 0.5)
    test.assertEqual(by_threshold[0.6]["false_confident"], 1)
    test.assertEqual(by_threshold[0.6]["confident_count"], 2)
    test.assertEqual(by_threshold[0.6]["coverage_rate"], 0.3333)
    test.assertEqual(by_threshold[0.8]["false_confident"], 1)
    test.assertEqual(by_threshold[0.8]["review_needed_count"], 4)
    test.assertEqual(by_threshold[0.9]["false_confident"], 0)
    test.assertEqual(by_threshold[0.9]["confident_count"], 1)
    test.assertEqual(by_threshold[0.9]["review_needed_count"], 5)
    test.assertEqual(by_threshold[0.9]["coverage_rate"], 0.1667)
    test.assertEqual(
        report["available_models"],
        [
            {"provider": "synth-prov", "model": "synth-model-a"},
            {"provider": "synth-prov", "model": "synth-model-b"},
        ],
    )


def _stores() -> tuple[MemoryRuns, MemoryDecisions]:
    return MemoryRuns(), MemoryDecisions()


def _plant(
    runs: object,
    decisions: object,
    finished: list[Run],
    queued: list[Run],
    rows: list[TeacherDecision],
) -> None:
    for run in finished:
        runs.insert(_shell(run))  # type: ignore[attr-defined]
        runs.finish(  # type: ignore[attr-defined]
            run.run_id,
            status=run.status,
            error_code=run.error_code,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            external_match=run.external_match,
            page_match=run.page_match,
            suggestions=run.suggestions,
        )
    for run in queued:
        runs.insert(run)  # type: ignore[attr-defined]
    for row in rows:
        decisions.replace(row)  # type: ignore[attr-defined]


def _mixed_finished() -> list[Run]:
    paper = PAPER
    first = _run(
        "run-synth-a",
        model="synth-model-a",
        status="succeeded",
        started="2026-11-25T00:00:00Z",
        external="consistent",
        page="mismatch",
        tokens=(11, 2),
        suggestions=(
            _item("run-synth-a", 1, "correct", "local", 0.95, paper),
            _item("run-synth-a", 2, "incorrect", "model", 0.55, paper),
            _item("run-synth-a", 3, "unsure", "model", 0.3, paper),
            _item("run-synth-a", 4, "unsure", "local", 0.2, paper, unreadable=True),
            _item("run-synth-a", 5, "partial", "local", 0.8, paper),
        ),
    )
    failed = _run(
        "run-synth-b",
        model="synth-model-b",
        status="failed",
        started="2026-11-25T00:01:00Z",
        error="timeout",
        tokens=(5, 1),
    )
    later = _run(
        "run-synth-d",
        model="synth-model-a",
        status="succeeded",
        started="2026-11-25T00:03:00Z",
        external="mismatch",
        page="unread",
        tokens=(4, 4),
        suggestions=(_item("run-synth-d", 7, "correct", "model", 0.85, paper),),
    )
    return [first, failed, later]


def _queued() -> Run:
    return _run(
        "run-synth-c",
        model="synth-model-a",
        status="queued",
        started="2026-11-25T00:02:00Z",
    )


def _mixed_decisions() -> list[TeacherDecision]:
    linked = "2026-11-25T01:00:00Z"
    return [
        _decision("decision-synth-void", 1, "incorrect", "revised", "2026-11-25T00:30:00Z", run_id="run-synth-a", ai_verdict="correct", confidence=0.95),
        _decision("decision-synth-1", 1, "correct", "adopted", linked, run_id="run-synth-a", ai_verdict="correct", confidence=0.95),
        _decision("decision-synth-2", 2, "correct", "revised", linked, run_id="run-synth-a", ai_verdict="incorrect", confidence=0.55),
        _decision("decision-synth-3", 3, "blank", "revised", linked, run_id="run-synth-a", ai_verdict="unsure", confidence=0.3),
        _decision("decision-synth-4", 4, "blank", "revised", linked, run_id="run-synth-a", ai_verdict="unsure", confidence=0.2),
        _decision("decision-synth-5", 5, "partial", "revised", linked, run_id="run-synth-a", ai_verdict="partial", confidence=0.8),
        _decision("decision-synth-6", 6, "correct", "manual", linked),
        _decision("decision-synth-7", 7, "incorrect", "revised", linked, run_id="run-synth-d", ai_verdict="correct", confidence=0.85),
        _decision("decision-synth-8", 8, "correct", "revised", linked, run_id="run-synth-b", ai_verdict="correct", confidence=0.5),
    ]


def _false_run() -> Run:
    return _run(
        "run-synth-false",
        model="synth-model-a",
        status="succeeded",
        started="2026-11-25T02:00:00Z",
        external="consistent",
        page="consistent",
        tokens=(2, 1),
        suggestions=(_item("run-synth-false", 1, "correct", "model", 0.85, PAPER, transcription=BAIT_TRANSCRIPTION),),
    )


def _false_decision(comment: str = "", corrected: str = "") -> TeacherDecision:
    return _decision(
        "decision-synth-false",
        1,
        "incorrect",
        "revised",
        "2026-11-25T02:01:00Z",
        run_id="run-synth-false",
        ai_verdict="correct",
        confidence=0.85,
        comment=comment or BAIT_STUDENT,
        corrected=corrected,
    )


def _voided_false() -> TeacherDecision:
    return _decision(
        "decision-synth-void-false",
        1,
        "correct",
        "adopted",
        "2026-11-25T02:00:30Z",
        run_id="run-synth-false",
        ai_verdict="correct",
        confidence=0.85,
    )


def _finished(run: Run) -> Run:
    return run


def _run(
    run_id: str,
    *,
    model: str,
    status: str,
    started: str,
    external: str = "",
    page: str = "",
    error: str = "",
    tokens: tuple[int | None, int | None] = (None, None),
    suggestions: tuple[Suggestion, ...] = (),
) -> Run:
    return Run(
        run_id=run_id,
        intake_id=INTAKE,
        provider="synth-prov",
        model=model,
        prompt_version="transcribe-v1/judge-v1",
        status=status,
        error_code=error,
        started_at=started,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        external_match=external,
        page_match=page,
        suggestions=suggestions,
    )


def _shell(run: Run) -> Run:
    return Run(
        run_id=run.run_id,
        intake_id=run.intake_id,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        status="queued",
        started_at=run.started_at,
    )


def _item(
    run_id: str,
    order_no: int,
    verdict: str,
    judged_by: str,
    confidence: float,
    paper_id: str,
    *,
    unreadable: bool = False,
    transcription: str = "",
) -> Suggestion:
    return Suggestion(
        run_id=run_id,
        paper_id=paper_id,
        order_no=order_no,
        transcription=transcription,
        unreadable=unreadable,
        confidence=confidence,
        verdict=verdict,
        reason="synth-reason",
        judged_by=judged_by,
    )


def _decision(
    decision_id: str,
    order_no: int,
    verdict: str,
    source: str,
    decided_at: str,
    *,
    run_id: str = "",
    ai_verdict: str = "",
    confidence: float | None = None,
    comment: str = "",
    corrected: str = "",
) -> TeacherDecision:
    return TeacherDecision(
        decision_id=decision_id,
        paper_id=PAPER,
        order_no=order_no,
        verdict=verdict,
        source=source,
        decided_by="teacher-synth",
        decided_at=decided_at,
        ai_run_id=run_id,
        ai_verdict=ai_verdict,
        ai_confidence=confidence,
        corrected_transcription=corrected,
        comment=comment,
    )


def _app() -> object:
    env = {
        "K12_PG_DSN": "",
        "K12_ENV": "development",
        "K12_AI_PROVIDER": "mock",
        "K12_AI_API_KEY": "",
        "K12_AI_REVIEW_THRESHOLD": "",
        "K12_SYNTH_SECRET": SYNTH_SECRET,
    }
    with mock.patch.dict(os.environ, env, clear=False):
        return create_app(seed=True)


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/login", json={"username": username, "secret": SYNTH_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.text)
    return str(response.json()["csrf_token"])
