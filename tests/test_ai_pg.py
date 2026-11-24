"""V015 on the scratch database. Skipped unless K12_PG_DSN is set."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.ai.domain.records import Run, Suggestion
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok, StoreFault


class _Capture:
    def log(self, event: LogEvent) -> None:
        return


class AiPgTest(unittest.TestCase):
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

    def tearDown(self) -> None:
        pool = getattr(self, "pool", None)
        if pool is not None:
            self._cleanup()
            pool.close()
        directory = getattr(self, "directory", None)
        if directory is not None:
            directory.cleanup()

    def test_v015_up_down_up(self) -> None:
        self.pool.close()
        self.pool = None
        _v015_round_trip(self.dsn)

    def test_pg_run_keeps_the_match_and_not_the_read_number(self) -> None:
        from backend.ai.adapters.pg_runs import PgRuns
        from backend.practice.application.intake_photo import upload_intake
        from backend.practice.domain.item import PracticeItem
        from backend.practice.domain.paper import freeze_paper

        paper_id = "paper-r6-pg"
        frozen = freeze_paper(
            paper_id=paper_id,
            teacher_id="teacher-r6-pg",
            student_id="student-r6-pg",
            subject_id="math",
            question_version_id="qv-r6-pg",
            answer_version_id="av-r6-pg",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-r6-pg",
            item_order=("sq-1",),
            printed_external_id="synth-bait-ext",
            issued_on="2026-11-24",
        )
        self.assertNotIsInstance(frozen, Err)
        assert not isinstance(frozen, Err)
        self.papers.append(paper_id)
        self.items.place_composed(
            frozen,
            (
                PracticeItem(
                    paper_id=paper_id,
                    order_no=1,
                    question_version_id="qv-r6-pg",
                    answer_version_id="av-r6-pg",
                    page_no=1,
                ),
            ),
        )
        uploaded = upload_intake(
            paper_id=paper_id,
            page_no=1,
            body=b"\xff\xd8" + b"IMAGE-BYTES-R6" + b"\xff\xd9",
            content_type="image/jpeg",
            located_by="manual",
            qr_text="",
            replace=False,
            actor_id="teacher-r6-pg",
            actor_role="teacher",
            practice=self.practice,
            items=self.items,
            files=self.files,
            intake=self.intake,
            logger=_Capture(),
            request_id="req-r6-pg",
        )
        self.assertIsInstance(uploaded, Ok)
        assert isinstance(uploaded, Ok)
        self.file_ids.append(str(uploaded.value["file_id"]))
        intake_id = str(uploaded.value["intake_id"])
        runs = PgRuns(self.pool)
        first = _run("run-r6-pg-a", intake_id)
        runs.insert(first)
        with self.assertRaises(StoreFault) as caught:
            runs.insert(_run("run-r6-pg-b", intake_id))
        self.assertEqual(caught.exception.code, "ai_run_in_progress")
        self.assertTrue(runs.mark_running(first.run_id))
        self.assertFalse(runs.mark_running(first.run_id))
        runs.finish(
            first.run_id,
            status="succeeded",
            error_code="",
            input_tokens=4,
            output_tokens=2,
            external_match="consistent",
            page_match="unread",
            suggestions=(
                Suggestion(
                    run_id=first.run_id,
                    paper_id=paper_id,
                    order_no=1,
                    transcription="2",
                    unreadable=False,
                    confidence=0.91,
                    verdict="correct",
                    reason="与标准答案一致",
                    judged_by="local",
                ),
            ),
        )
        saved = runs.get(first.run_id)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.external_match, "consistent")
        self.assertEqual(saved.page_match, "unread")
        self.assertEqual(saved.suggestions[0].transcription, "2")
        self.assertGreaterEqual(runs.count_started_on(datetime.now(timezone.utc).strftime("%Y-%m-%d")), 1)
        self.assertNotIn("synth-bait-ext", _ai_text(self.pool, first.run_id))
        third = _run("run-r6-pg-c", intake_id)
        runs.insert(third)
        self.assertGreaterEqual(runs.interrupt_open(), 1)
        interrupted = runs.get(third.run_id)
        self.assertIsNotNone(interrupted)
        assert interrupted is not None
        self.assertEqual(interrupted.status, "failed")
        self.assertEqual(interrupted.error_code, "interrupted")

    def _cleanup(self) -> None:
        papers = tuple(self.papers)
        file_ids = tuple(dict.fromkeys(self.file_ids))
        if not papers and not file_ids:
            return
        statements = (
            "DELETE FROM ai_suggestion WHERE paper_id = ANY(%s)",
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


def _run(run_id: str, intake_id: str) -> Run:
    return Run(
        run_id=run_id,
        intake_id=intake_id,
        provider="mock",
        model="mock",
        prompt_version="transcribe-v1/judge-v1",
        status="queued",
        started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _ai_text(pool: object, run_id: str) -> str:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        run = conn.execute(
            """
            SELECT coalesce(external_match, '') || ' ' || coalesce(page_match, '') || ' ' ||
                   coalesce(error_code, '') || ' ' || provider || ' ' || model
            FROM ai_run WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
        suggestion = conn.execute(
            "SELECT coalesce(string_agg(transcription || ' ' || reason, ' '), '') FROM ai_suggestion WHERE run_id = %s",
            (run_id,),
        ).fetchone()
    left = "" if run is None else str(run[0])
    right = "" if suggestion is None else str(suggestion[0])
    return left + " " + right


def _v015_round_trip(dsn: str) -> None:
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    item = next(row for row in discover(root) if row.version == "V015")
    _expect_v015(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V015",))
        _expect_v015(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v015(dsn, True)


def _expect_v015(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        run = conn.execute("SELECT to_regclass('public.ai_run')").fetchone()
        suggestion = conn.execute("SELECT to_regclass('public.ai_suggestion')").fetchone()
        intake = conn.execute("SELECT to_regclass('public.intake_page')").fetchone()
    found = run is not None and run[0] is not None and suggestion is not None and suggestion[0] is not None
    intake_ok = intake is not None and intake[0] is not None
    if not intake_ok:
        raise AssertionError("intake_page missing")
    if present and not found:
        raise AssertionError("V015 objects missing")
    if not present and found:
        raise AssertionError("V015 objects still present")
