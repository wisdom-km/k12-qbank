"""V017 on the scratch database. Skipped unless K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest

from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err
from backend.practice.domain.decision import TeacherDecision


class _Capture:
    def log(self, event: LogEvent) -> None:
        return


class DecisionPgTest(unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from psycopg_pool import ConnectionPool

        from backend.bootstrap.compose import repo_root
        from backend.bootstrap.migrate import migrate
        from backend.practice.adapters.pg_items import PgPracticeItems
        from backend.practice.adapters.pg_practice import PgPractice

        self.dsn = os.environ["K12_PG_DSN"]
        migrate(self.dsn, repo_root(), "up")
        self.pool = ConnectionPool(self.dsn, min_size=1, max_size=1, open=True)
        self.practice = PgPractice(self.pool)
        self.items = PgPracticeItems(self.pool)
        self.papers: list[str] = []

    def tearDown(self) -> None:
        pool = getattr(self, "pool", None)
        if pool is not None:
            self._cleanup()
            pool.close()

    def test_v017_up_down_up(self) -> None:
        self.pool.close()
        self.pool = None
        _v017_round_trip(self.dsn)

    def test_pg_one_current_row(self) -> None:
        from backend.practice.adapters.pg_decision import PgDecisions
        from backend.practice.domain.item import PracticeItem
        from backend.practice.domain.paper import freeze_paper

        paper_id = "paper-r7-pg"
        frozen = freeze_paper(
            paper_id=paper_id,
            teacher_id="teacher-r7-pg",
            student_id="student-r7-pg",
            subject_id="math",
            question_version_id="qv-r7-pg",
            answer_version_id="av-r7-pg",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-r7-pg",
            item_order=("sq-1",),
            printed_external_id="synth-r7-pg",
            issued_on="2026-11-25",
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
                    question_version_id="qv-r7-pg",
                    answer_version_id="av-r7-pg",
                    page_no=1,
                ),
            ),
        )
        decisions = PgDecisions(self.pool)
        decisions.replace(_row("decision-r7-pg-a", paper_id, "2026-11-25T00:00:00Z", "correct"))
        decisions.replace(_row("decision-r7-pg-b", paper_id, "2026-11-25T00:01:00Z", "incorrect"))
        current = decisions.current(paper_id, 1)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.verdict, "incorrect")
        self.assertEqual(current.source, "manual")
        self.assertEqual(current.ai_run_id, "")
        self.assertIsNone(current.ai_confidence)
        self.assertEqual([row.decision_id for row in decisions.currents(paper_id)], ["decision-r7-pg-b"])
        history = decisions.history(paper_id)
        self.assertEqual([row.decision_id for row in history], ["decision-r7-pg-a", "decision-r7-pg-b"])
        self.assertTrue(history[0].voided_at)
        self.assertEqual(history[1].voided_at, "")

    def _cleanup(self) -> None:
        papers = tuple(self.papers)
        if not papers:
            return
        statements = (
            "DELETE FROM teacher_decision WHERE paper_id = ANY(%s)",
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
                    conn.execute(statement, (list(papers),))


def _row(decision_id: str, paper_id: str, decided_at: str, verdict: str) -> TeacherDecision:
    return TeacherDecision(
        decision_id=decision_id,
        paper_id=paper_id,
        order_no=1,
        verdict=verdict,
        source="manual",
        decided_by="teacher-r7-pg",
        decided_at=decided_at,
    )


def _v017_round_trip(dsn: str) -> None:
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    item = next(row for row in discover(root) if row.version == "V017")
    _expect_v017(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V017",))
        _expect_v017(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v017(dsn, True)


def _expect_v017(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        found = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'teacher_decision'
            """
        ).fetchone()
    if present and found is None:
        raise AssertionError("teacher_decision is missing")
    if not present and found is not None:
        raise AssertionError("teacher_decision is still present")
