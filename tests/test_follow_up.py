"""Follow-up papers from current teacher decisions. Memory always runs. PostgreSQL runs when K12_PG_DSN is set."""

from __future__ import annotations

import json
import os
import unittest
import uuid
from dataclasses import replace

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.catalog.domain.publication import Publication
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.adapters.files import MemoryFiles
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice
from backend.practice.adapters.memory_decision import MemoryDecisions
from backend.practice.adapters.memory_items import MemoryComposedWriter, MemoryPracticeItems
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.api import IssuePaperCommand
from backend.practice.application.follow_up import issue_follow_up
from backend.practice.application.open_multi import open_multi_paper
from backend.practice.application.open_paper import open_paper
from backend.practice.domain.decision import TeacherDecision
from backend.practice.domain.paper import Paper, freeze_paper

_TEACHER = "teacher-synth-r8"
_OTHER = "teacher-synth-r8-other"
_STUDENT = "student-synth-r8"
_SUBJECT = "math"
_STEM = "synth-r8-stem"
_ANSWER = "synth-a"
_REVIEW = "rev-synth-r8"


class _Log:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class _Deny:
    def allow(self, teacher_id: str, student_id: str, subject_id: str) -> bool:
        return False


class FollowUpCases:
    approvals: object
    publications: object
    practice: object
    items: object
    writer: object
    decisions: object
    auth: MemoryAuth
    files: MemoryFiles
    renderer: StdPdf
    logger: _Log
    ids: list[str]

    def test_omitted_orders_skip_correct_and_unconfirmed(self) -> None:
        paper = self._source(
            ("q-synth-r8-auto-1", "q-synth-r8-auto-2", "q-synth-r8-auto-3", "q-synth-r8-auto-4", "q-synth-r8-auto-5"),
            {1: "incorrect", 2: "correct", 4: "partial", 5: "blank"},
        )
        before = self._freeze_source(paper.paper_id)
        opened = self._follow(paper.paper_id)
        self.assertIsInstance(opened, Ok)
        assert isinstance(opened, Ok)
        new = opened.value.paper
        self.assertNotEqual(new.paper_id, paper.paper_id)
        self.assertEqual(new.source_paper_id, paper.paper_id)
        self.assertEqual(new.student_id, paper.student_id)
        self.assertEqual(new.review_version_id, paper.review_version_id)
        copied = [row.question_version_id for row in self.items.items_of(new.paper_id)]  # type: ignore[attr-defined]
        self.assertEqual(copied, ["q-synth-r8-auto-1", "q-synth-r8-auto-4", "q-synth-r8-auto-5"])
        self.assertIsNotNone(new.file_id)
        self.assertIsNone(opened.value.render_code)
        self._assert_source_unchanged(paper.paper_id, before)
        detail = self._audit_detail()
        self.assertEqual(
            set(detail),
            {"source_paper_id", "paper_id", "item_count"},
        )
        self.assertEqual(detail["item_count"], 3)
        self.assertNotIn(_STUDENT, json.dumps(detail))
        self.assertNotIn(_STEM, json.dumps(self.logger.events[-1].fields()))
        self.assertNotIn(_ANSWER, json.dumps(self.logger.events[-1].fields()))

    def test_explicit_orders_can_drop_or_include_confirmed_items(self) -> None:
        paper = self._source(
            ("q-synth-r8-pick-1", "q-synth-r8-pick-2", "q-synth-r8-pick-3"),
            {1: "incorrect", 2: "incorrect", 3: "correct"},
        )
        dropped = self._follow(paper.paper_id, [2])
        self.assertIsInstance(dropped, Ok)
        assert isinstance(dropped, Ok)
        self.assertEqual(
            [row.question_version_id for row in self.items.items_of(dropped.value.paper.paper_id)],  # type: ignore[attr-defined]
            ["q-synth-r8-pick-2"],
        )
        included = self._follow(paper.paper_id, [3, 1])
        self.assertIsInstance(included, Ok)
        assert isinstance(included, Ok)
        self.assertEqual(
            [row.question_version_id for row in self.items.items_of(included.value.paper.paper_id)],  # type: ignore[attr-defined]
            ["q-synth-r8-pick-1", "q-synth-r8-pick-3"],
        )
        self.assertEqual(included.value.paper.source_paper_id, paper.paper_id)

    def test_explicit_orders_reject_unknown_duplicate_and_unconfirmed(self) -> None:
        paper = self._source(
            ("q-synth-r8-bad-1", "q-synth-r8-bad-2"),
            {1: "incorrect"},
        )
        before = {row.paper_id for row in self.practice.list_papers()}  # type: ignore[attr-defined]
        missing = self._follow(paper.paper_id, [9])
        duplicate = self._follow(paper.paper_id, [1, 1])
        zero = self._follow(paper.paper_id, [0])
        unconfirmed = self._follow(paper.paper_id, [2])
        self.assertEqual(missing.code, "invalid_order_no")  # type: ignore[union-attr]
        self.assertEqual(duplicate.code, "invalid_order_no")  # type: ignore[union-attr]
        self.assertEqual(zero.code, "invalid_order_no")  # type: ignore[union-attr]
        self.assertEqual(unconfirmed.code, "decision_required")  # type: ignore[union-attr]
        after = {row.paper_id for row in self.practice.list_papers()}  # type: ignore[attr-defined]
        self.assertEqual(before, after)

    def test_all_correct_or_ungraded_has_nothing_to_retry(self) -> None:
        correct = self._source(("q-synth-r8-ok-1", "q-synth-r8-ok-2"), {1: "correct", 2: "correct"})
        bare = self._source(("q-synth-r8-bare-1",), {})
        self.assertEqual(self._follow(correct.paper_id).code, "no_retry_items")  # type: ignore[union-attr]
        self.assertEqual(self._follow(bare.paper_id).code, "no_retry_items")  # type: ignore[union-attr]

    def test_missing_paper_other_teacher_and_revoked_grant(self) -> None:
        paper = self._source(("q-synth-r8-auth-1",), {1: "incorrect"})
        missing = self._follow("paper-synth-r8-missing")
        other = self._follow(paper.paper_id, actor=_OTHER)
        revoked = self._follow(paper.paper_id, auth=_Deny())
        self.assertEqual(missing.code, "not_found")  # type: ignore[union-attr]
        self.assertEqual(other.code, "permission_denied")  # type: ignore[union-attr]
        self.assertEqual(revoked.code, "permission_denied")  # type: ignore[union-attr]

    def test_one_item_uses_single_issue_and_two_use_multi(self) -> None:
        one = self._source(("q-synth-r8-one-1", "q-synth-r8-one-2"), {1: "incorrect", 2: "correct"})
        single = self._follow(one.paper_id)
        self.assertIsInstance(single, Ok)
        assert isinstance(single, Ok)
        self.assertEqual(len(self.items.items_of(single.value.paper.paper_id)), 1)  # type: ignore[attr-defined]
        many = self._source(("q-synth-r8-many-1", "q-synth-r8-many-2"), {1: "incorrect", 2: "blank"})
        multi = self._follow(many.paper_id)
        self.assertIsInstance(multi, Ok)
        assert isinstance(multi, Ok)
        self.assertEqual(len(self.items.items_of(multi.value.paper.paper_id)), 2)  # type: ignore[attr-defined]
        self.assertEqual(multi.value.paper.source_paper_id, many.paper_id)

    def test_legacy_paper_without_items_uses_the_frozen_question(self) -> None:
        paper = self._legacy("incorrect")
        opened = self._follow(paper.paper_id)
        self.assertIsInstance(opened, Ok)
        assert isinstance(opened, Ok)
        copied = self.items.items_of(opened.value.paper.paper_id)  # type: ignore[attr-defined]
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0].question_version_id, paper.question_version_id)
        self.assertEqual(self.items.items_of(paper.paper_id), ())  # type: ignore[attr-defined]

    def test_retired_question_writes_no_paper(self) -> None:
        paper = self._source(("q-synth-r8-retired", "q-synth-r8-retired-b"), {1: "incorrect", 2: "partial"})
        current = self.approvals.read_snapshot("q-synth-r8-retired")  # type: ignore[attr-defined]
        self.approvals.put(replace(current, retired=True))  # type: ignore[attr-defined]
        before = {row.paper_id for row in self.practice.list_papers()}  # type: ignore[attr-defined]
        refused = self._follow(paper.paper_id)
        after = {row.paper_id for row in self.practice.list_papers()}  # type: ignore[attr-defined]
        self.assertEqual(refused.code, "retired")  # type: ignore[union-attr]
        self.assertEqual(before, after)

    def test_production_does_not_bind_an_attempt(self) -> None:
        paper = self._source(("q-synth-r8-prod",), {1: "incorrect"})
        self.assertIsNotNone(self.practice.find_answer_for_paper(paper.paper_id))  # type: ignore[attr-defined]
        opened = self._follow(paper.paper_id, bind=False)
        self.assertIsInstance(opened, Ok)
        assert isinstance(opened, Ok)
        self.assertEqual(opened.value.fixture_answer_id, "")
        self.assertIsNone(self.practice.find_answer_for_paper(opened.value.paper.paper_id))  # type: ignore[attr-defined]
        self.assertIsNotNone(self.practice.find_answer_for_paper(paper.paper_id))  # type: ignore[attr-defined]

    def test_review_version_can_be_overridden(self) -> None:
        paper = self._source(("q-synth-r8-rev",), {1: "incorrect"})
        opened = self._follow(paper.paper_id, review="rev-synth-r8-next")
        self.assertIsInstance(opened, Ok)
        assert isinstance(opened, Ok)
        self.assertEqual(opened.value.paper.review_version_id, "rev-synth-r8-next")

    def _follow(
        self,
        paper_id: str,
        order_nos: list[int] | None = None,
        *,
        actor: str = _TEACHER,
        auth: object | None = None,
        bind: bool = True,
        review: str = "",
    ) -> Ok[object] | Err:
        opened = issue_follow_up(
            paper_id,
            order_nos=list(order_nos or []),
            review_version_id=review,
            actor_teacher_id=actor,
            approvals=self.approvals,  # type: ignore[arg-type]
            auth=self.auth if auth is None else auth,  # type: ignore[arg-type]
            store=self.practice,  # type: ignore[arg-type]
            items=self.items,  # type: ignore[arg-type]
            decisions=self.decisions,
            writer=self.writer,  # type: ignore[arg-type]
            files=self.files,
            renderer=self.renderer,
            publications=self.publications,  # type: ignore[arg-type]
            logger=self.logger,
            request_id="req-synth-r8",
            qr_printed=False,
            printed_external_id="",
            attempt_text="synth-attempt" if bind else "",
            bind_attempt=bind,
        )
        if isinstance(opened, Ok):
            self.ids.append(opened.value.paper.paper_id)
        return opened

    def _source(self, versions: tuple[str, ...], verdicts: dict[int, str]) -> Paper:
        for version_id in versions:
            self.approvals.put(_snapshot(version_id))  # type: ignore[attr-defined]
            self._activate(version_id)
        paper_id = "paper-synth-r8-" + uuid.uuid4().hex
        if len(versions) == 1:
            self.ids.append(paper_id)
            opened = open_paper(
                IssuePaperCommand(
                    teacher_id=_TEACHER,
                    student_id=_STUDENT,
                    subject_id=_SUBJECT,
                    question_version_id=versions[0],
                    review_version_id=_REVIEW,
                ),
                self.approvals,  # type: ignore[arg-type]
                self.auth,
                self.practice,  # type: ignore[arg-type]
                self.files,
                self.renderer,
                self.logger,
                "req-synth-r8-source",
                lambda paper_id=paper_id: paper_id,
                actor_teacher_id=_TEACHER,
                attempt_text="synth-attempt",
                publications=self.publications,  # type: ignore[arg-type]
                items=self.items,  # type: ignore[arg-type]
            )
        else:
            opened = open_multi_paper(
                teacher_id=_TEACHER,
                student_id=_STUDENT,
                subject_id=_SUBJECT,
                review_version_id=_REVIEW,
                question_version_ids=versions,
                qr_printed=False,
                printed_external_id="",
                approvals=self.approvals,  # type: ignore[arg-type]
                auth=self.auth,
                store=self.practice,  # type: ignore[arg-type]
                items=self.items,  # type: ignore[arg-type]
                writer=self.writer,  # type: ignore[arg-type]
                files=self.files,
                renderer=self.renderer,
                logger=self.logger,
                request_id="req-synth-r8-source",
                attempt_text="synth-attempt",
                publications=self.publications,  # type: ignore[arg-type]
            )
        self.assertIsInstance(opened, Ok)  # type: ignore[attr-defined]
        assert isinstance(opened, Ok)
        if len(versions) != 1:
            self.ids.append(opened.value.paper.paper_id)
        for order_no, verdict in verdicts.items():
            self.decisions.replace(_decision(opened.value.paper.paper_id, order_no, verdict))  # type: ignore[attr-defined]
        return opened.value.paper

    def _legacy(self, verdict: str) -> Paper:
        version_id = "q-synth-r8-legacy-" + uuid.uuid4().hex[:8]
        self.approvals.put(_snapshot(version_id))  # type: ignore[attr-defined]
        self._activate(version_id)
        paper_id = "paper-synth-r8-" + uuid.uuid4().hex
        frozen = freeze_paper(
            paper_id=paper_id,
            teacher_id=_TEACHER,
            student_id=_STUDENT,
            subject_id=_SUBJECT,
            question_version_id=version_id,
            answer_version_id="a-" + version_id,
            asset_ids=("page-synth",),
            layout_template_id="layout-1",
            review_version_id=_REVIEW,
            item_order=("sq-1",),
            formula="",
        )
        self.assertNotIsInstance(frozen, Err)  # type: ignore[attr-defined]
        assert not isinstance(frozen, Err)
        self.practice.place_paper(frozen)  # type: ignore[attr-defined]
        self.ids.append(paper_id)
        self.decisions.replace(_decision(paper_id, 1, verdict))  # type: ignore[attr-defined]
        return frozen

    def _activate(self, version_id: str) -> None:
        self.publications.put(  # type: ignore[attr-defined]
            Publication(
                publication_id="pub-" + version_id,
                question_version_id=version_id,
                answer_version_id="a-" + version_id,
                subject_id=_SUBJECT,
                status="active",
            )
        )

    def _freeze_source(self, paper_id: str) -> tuple[Paper, tuple[object, ...], tuple[object, ...]]:
        paper = self.practice.get_paper(paper_id)  # type: ignore[attr-defined]
        assert paper is not None
        return (
            paper,
            self.items.items_of(paper_id),  # type: ignore[attr-defined]
            self.decisions.history(paper_id),  # type: ignore[attr-defined]
        )

    def _assert_source_unchanged(
        self, paper_id: str, before: tuple[Paper, tuple[object, ...], tuple[object, ...]]
    ) -> None:
        self.assertEqual(self.practice.get_paper(paper_id), before[0])  # type: ignore[attr-defined]
        self.assertEqual(self.items.items_of(paper_id), before[1])  # type: ignore[attr-defined]
        self.assertEqual(self.decisions.history(paper_id), before[2])  # type: ignore[attr-defined]

    def _audit_detail(self) -> dict[str, object]:
        found = [row for row in self.logger.events if row.event == "follow_up_paper_issued"]
        self.assertTrue(found)  # type: ignore[attr-defined]
        return json.loads(found[-1].detail)


class MemoryFollowUpTest(FollowUpCases, unittest.TestCase):
    def setUp(self) -> None:
        self.approvals = MemoryApprovals()
        self.publications = MemoryPublications()
        self.practice = MemoryPractice()
        self.items = MemoryPracticeItems()
        self.writer = MemoryComposedWriter(self.practice, self.items)
        self.decisions = MemoryDecisions()
        self.auth = MemoryAuth()
        self.auth.grant(_TEACHER, _STUDENT, _SUBJECT)
        self.auth.grant(_OTHER, _STUDENT, _SUBJECT)
        self.files = MemoryFiles()
        self.renderer = StdPdf()
        self.logger = _Log()
        self.ids = []


class PgFollowUpTest(FollowUpCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_approvals import PgApprovals
        from backend.catalog.adapters.pg_publications import PgPublications
        from backend.practice.adapters.pg_decision import PgDecisions
        from backend.practice.adapters.pg_items import PgPracticeItems
        from backend.practice.adapters.pg_practice import PgPractice

        self.pool = _pool()
        self.approvals = PgApprovals(self.pool)
        self.publications = PgPublications(self.pool)
        self.practice = PgPractice(self.pool)
        self.items = PgPracticeItems(self.pool)
        self.writer = self.items
        self.decisions = PgDecisions(self.pool)
        self.auth = MemoryAuth()
        self.auth.grant(_TEACHER, _STUDENT, _SUBJECT)
        self.auth.grant(_OTHER, _STUDENT, _SUBJECT)
        self.files = MemoryFiles()
        self.renderer = StdPdf()
        self.logger = _Log()
        self.ids = []

    def tearDown(self) -> None:
        pool = getattr(self, "pool", None)
        ids = getattr(self, "ids", None)
        if pool is None or not ids:
            return
        with pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                conn.execute("DELETE FROM teacher_decision WHERE paper_id = ANY(%s)", (ids,))
                conn.execute("DELETE FROM practice_item_box WHERE paper_id = ANY(%s)", (ids,))
                conn.execute("DELETE FROM practice_item WHERE paper_id = ANY(%s)", (ids,))
                conn.execute("DELETE FROM attempts WHERE paper_id = ANY(%s)", (ids,))
                conn.execute("DELETE FROM confirmations WHERE paper_id = ANY(%s)", (ids,))
                conn.execute("DELETE FROM paper_pages WHERE paper_id = ANY(%s)", (ids,))
                conn.execute("DELETE FROM papers WHERE paper_id = ANY(%s)", (ids,))


def _snapshot(version_id: str) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=version_id,
        answer_version_id="a-" + version_id,
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        question_approved=True,
        answer_approved=True,
        retired=False,
        subject_id=_SUBJECT,
        item_order=("sq-1",),
        stem=_STEM,
        answer_text=_ANSWER,
        type="single_choice",
        options=("synth-opt",),
    )


def _decision(paper_id: str, order_no: int, verdict: str) -> TeacherDecision:
    return TeacherDecision(
        decision_id="decision-synth-r8-" + paper_id + "-" + str(order_no),
        paper_id=paper_id,
        order_no=order_no,
        verdict=verdict,
        source="manual",
        decided_by=_TEACHER,
        decided_at="2026-11-25T00:00:00Z",
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
