"""Accuracy reads on the scratch database. Skipped unless K12_PG_DSN is set."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dataclasses import replace

from backend.ai.application.accuracy import accuracy_report
from backend.ai.domain.records import Run
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from tests.test_ai_accuracy import (
    PAPER,
    _assert_mixed,
    _false_decision,
    _false_run,
    _finished,
    _mixed_decisions,
    _mixed_finished,
    _plant,
    _queued,
    _voided_false,
)


class _Capture:
    def log(self, event: LogEvent) -> None:
        return


class AccuracyPgTest(unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from psycopg_pool import ConnectionPool

        from backend.bootstrap.compose import repo_root
        from backend.bootstrap.migrate import migrate
        from backend.practice.adapters.pg_files import PgFiles
        from backend.practice.adapters.pg_intake import PgIntake
        from backend.practice.adapters.pg_items import PgPracticeItems
        from backend.practice.adapters.pg_practice import PgPractice

        self.dsn = os.environ["K12_PG_DSN"]
        migrate(self.dsn, repo_root(), "up")
        self.pool = ConnectionPool(self.dsn, min_size=1, max_size=1, open=True)
        self.directory = tempfile.TemporaryDirectory()
        self.files = PgFiles(self.pool, Path(self.directory.name))
        self.intake = PgIntake(self.pool)
        self.practice = PgPractice(self.pool)
        self.items = PgPracticeItems(self.pool)
        self.papers: list[str] = []
        self.file_ids: list[str] = []
        self.intake_id = ""

    def tearDown(self) -> None:
        pool = getattr(self, "pool", None)
        if pool is not None:
            self._cleanup()
            pool.close()
        directory = getattr(self, "directory", None)
        if directory is not None:
            directory.cleanup()

    def test_mixed_counts_and_ordered_reads(self) -> None:
        from backend.ai.adapters.pg_runs import PgRuns
        from backend.practice.adapters.pg_decision import PgDecisions

        intake_id = self._parents()
        runs = PgRuns(self.pool)
        decisions = PgDecisions(self.pool)
        _plant(
            runs,
            decisions,
            [_bind(run, intake_id) for run in _mixed_finished()],
            [_bind(_queued(), intake_id)],
            _mixed_decisions(),
        )
        report = accuracy_report(runs, decisions)
        _assert_mixed(self, report)
        self.assertEqual(
            [row.run_id for row in runs.all_runs()],
            ["run-synth-a", "run-synth-b", "run-synth-c", "run-synth-d"],
        )
        self.assertEqual(len(runs.all_runs()[0].suggestions), 5)
        self.assertNotIn("decision-synth-void", [row.decision_id for row in decisions.all_current()])

    def test_one_confident_disagreement_drops_out_at_0_9(self) -> None:
        from backend.ai.adapters.pg_runs import PgRuns
        from backend.practice.adapters.pg_decision import PgDecisions

        intake_id = self._parents()
        runs = PgRuns(self.pool)
        decisions = PgDecisions(self.pool)
        _plant(
            runs,
            decisions,
            [_bind(_finished(_false_run()), intake_id)],
            [],
            [_voided_false(), _false_decision()],
        )
        report = accuracy_report(runs, decisions)
        by_threshold = {row["threshold"]: row for row in report["thresholds"]}
        self.assertEqual(by_threshold[0.6]["false_confident"], 1)
        self.assertEqual(by_threshold[0.8]["false_confident"], 1)
        self.assertEqual(by_threshold[0.9]["false_confident"], 0)
        self.assertEqual(by_threshold[0.9]["review_needed_count"], 1)
        self.assertNotIn("decision-synth-void-false", [row.decision_id for row in decisions.all_current()])

    def _parents(self) -> str:
        from backend.practice.application.intake_photo import upload_intake
        from backend.practice.domain.item import PracticeItem
        from backend.practice.domain.paper import freeze_paper

        frozen = freeze_paper(
            paper_id=PAPER,
            teacher_id="teacher-synth-acc",
            student_id="student-synth-acc",
            subject_id="math",
            question_version_id="qv-synth-acc",
            answer_version_id="av-synth-acc",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-synth-acc",
            item_order=("sq-synth-acc",),
            printed_external_id="synth-ext-acc",
            issued_on="2026-11-25",
        )
        self.assertNotIsInstance(frozen, Err)
        assert not isinstance(frozen, Err)
        self.papers.append(PAPER)
        self.items.place_composed(
            frozen,
            (
                PracticeItem(
                    paper_id=PAPER,
                    order_no=1,
                    question_version_id="qv-synth-acc",
                    answer_version_id="av-synth-acc",
                    page_no=1,
                ),
            ),
        )
        uploaded = upload_intake(
            paper_id=PAPER,
            page_no=1,
            body=b"\xff\xd8" + b"synth-acc" + b"\xff\xd9",
            content_type="image/jpeg",
            located_by="manual",
            qr_text="",
            replace=False,
            actor_id="teacher-synth-acc",
            actor_role="teacher",
            practice=self.practice,
            items=self.items,
            files=self.files,
            intake=self.intake,
            logger=_Capture(),
            request_id="req-synth-acc",
        )
        self.assertIsInstance(uploaded, Ok)
        assert isinstance(uploaded, Ok)
        self.file_ids.append(str(uploaded.value["file_id"]))
        intake_id = str(uploaded.value["intake_id"])
        self.intake_id = intake_id
        return intake_id

    def _cleanup(self) -> None:
        papers = tuple(self.papers)
        file_ids = tuple(dict.fromkeys(self.file_ids))
        if not papers and not file_ids:
            return
        statements = (
            "DELETE FROM ai_suggestion WHERE paper_id = ANY(%s)",
            "DELETE FROM teacher_decision WHERE paper_id = ANY(%s)",
            "DELETE FROM ai_run WHERE intake_id IN (SELECT intake_id FROM intake_page WHERE paper_id = ANY(%s))",
            "DELETE FROM intake_page WHERE paper_id = ANY(%s)",
            "DELETE FROM practice_item_box WHERE paper_id = ANY(%s)",
            "DELETE FROM practice_item WHERE paper_id = ANY(%s)",
            "DELETE FROM paper_pages WHERE paper_id = ANY(%s)",
            "DELETE FROM attempts WHERE paper_id = ANY(%s)",
            "DELETE FROM confirmations WHERE paper_id = ANY(%s)",
            "DELETE FROM papers WHERE paper_id = ANY(%s)",
        )
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                for statement in statements:
                    if papers:
                        conn.execute(statement, (list(papers),))
                if file_ids:
                    conn.execute("DELETE FROM files WHERE file_id = ANY(%s)", (list(file_ids),))


def _bind(run: Run, intake_id: str) -> Run:
    return replace(run, intake_id=intake_id)
