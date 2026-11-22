"""Multi-item practice contract. Memory always runs. PostgreSQL runs when K12_PG_DSN is set."""

from __future__ import annotations

import os
import unittest

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.catalog.application.retire_publication import retire_publication
from backend.catalog.domain.publication import Publication
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.adapters.files import MemoryFiles
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice
from backend.practice.adapters.memory_items import MemoryComposedWriter, MemoryPracticeItems
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.api import ConfirmCommand, IssuePaperCommand
from backend.practice.application.compose_multi import compose_multi_item_paper
from backend.practice.domain.confirm import PendingAnswer
from backend.practice.application.confirm_attempt import confirm_attempt
from backend.practice.application.render_paper import render_paper
from backend.practice.application.issue_paper import issue_paper
from backend.practice.application.open_paper import open_paper
from backend.practice.application.resolve_items import _resolve_items
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import Paper

_TEACHER = "teacher-synth"
_STUDENT = "student-synth"
_SUBJECT = "math"
_STEM = "计算：(-3)+5"


class _Log:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class PracticeItemCases:
    approvals: object
    practice: object
    items: object
    writer: object
    auth: MemoryAuth
    files: MemoryFiles
    renderer: StdPdf
    logger: _Log

    def test_single_item_paper_still_opens(self) -> None:
        self.approvals.put(_snapshot("q-d4-a", "a-d4-a"))  # type: ignore[attr-defined]
        self._activate("q-d4-a", "a-d4-a")
        issued = issue_paper(
            _command("q-d4-a"),
            self.approvals,  # type: ignore[arg-type]
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.logger,
            "req-d4-a",
            lambda: "paper-d4-a",
            actor_teacher_id=_TEACHER,
            publications=self.publications,  # type: ignore[attr-defined]
        )
        self.assertIsInstance(issued, Ok)  # type: ignore[attr-defined]
        paper = issued.value  # type: ignore[union-attr]
        self.assertEqual(self.items.items_of(paper.paper_id), ())  # type: ignore[attr-defined]
        resolved = _resolve_items(paper.paper_id, self.practice, self.items)  # type: ignore[arg-type]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].order_no, 1)
        self.assertEqual(resolved[0].question_version_id, paper.question_version_id)
        self.assertEqual(resolved[0].answer_version_id, paper.answer_version_id)
        self.assertIsNone(resolved[0].score)

    def test_multi_item_paper_freezes_order(self) -> None:
        paper_id = "paper-d4-b"
        specs = (("q-d4-b2", "a-d4-b2", 2), ("q-d4-b3", "a-d4-b3", 3), ("q-d4-b1", "a-d4-b1", 1))
        for question_id, answer_id, _order in specs:
            self.approvals.put(_snapshot(question_id, answer_id))  # type: ignore[attr-defined]
            self._activate(question_id, answer_id)
        given = tuple(_item(paper_id, order, question_id, answer_id) for question_id, answer_id, order in specs)
        placed = self._compose(paper_id, given)
        self.assertIsInstance(placed, Ok)  # type: ignore[attr-defined]
        paper = self.practice.get_paper(paper_id)  # type: ignore[attr-defined]
        self.assertEqual(paper.question_version_id, given[0].question_version_id)
        self.assertEqual(paper.answer_version_id, given[0].answer_version_id)
        first = _resolve_items(paper_id, self.practice, self.items)  # type: ignore[arg-type]
        second = _resolve_items(paper_id, self.practice, self.items)  # type: ignore[arg-type]
        self.assertEqual(first, second)
        self.assertEqual([item.order_no for item in first], [1, 2, 3])
        self.assertEqual([item.question_version_id for item in first], ["q-d4-b1", "q-d4-b2", "q-d4-b3"])
        self._assert_pages(paper_id, given)

    def test_multi_item_paper_rejects_single(self) -> None:
        paper_id = "paper-d4-c"
        refused = self._compose(paper_id, (_item(paper_id, 1, "q-d4-c", "a-d4-c"),))
        self.assertIsInstance(refused, Err)  # type: ignore[attr-defined]
        self.assertEqual(refused.code, "not_multi")  # type: ignore[union-attr]
        self._assert_absent(paper_id)

    def test_multi_item_rejects_unapproved_question(self) -> None:
        paper_id = "paper-d4-d"
        self.approvals.put(_snapshot("q-d4-d1", "a-d4-d1"))  # type: ignore[attr-defined]
        given = (
            _item(paper_id, 1, "q-d4-d1", "a-d4-d1"),
            _item(paper_id, 2, "q-d4-missing", "a-d4-missing"),
        )
        refused = self._compose(paper_id, given)
        self.assertIsInstance(refused, Err)  # type: ignore[attr-defined]
        self.assertEqual(refused.code, "question_not_approved")  # type: ignore[union-attr]
        self.assertIsNone(self.approvals.read_snapshot("q-d4-missing"))  # type: ignore[attr-defined]
        self._assert_absent(paper_id)

    def test_multi_item_rejects_question_flag_false(self) -> None:
        paper_id = "paper-d4-e1"
        self.approvals.put(_snapshot("q-d4-e1a", "a-d4-e1a"))  # type: ignore[attr-defined]
        self.approvals.put(_snapshot("q-d4-e1b", "a-d4-e1b", question_approved=False, answer_approved=True))  # type: ignore[attr-defined]
        stored = self.approvals.read_snapshot("q-d4-e1b")  # type: ignore[attr-defined]
        self.assertIsNotNone(stored)
        self.assertFalse(stored.question_approved)  # type: ignore[union-attr]
        refused = self._compose(
            paper_id,
            (
                _item(paper_id, 1, "q-d4-e1a", "a-d4-e1a"),
                _item(paper_id, 2, "q-d4-e1b", "a-d4-e1b"),
            ),
        )
        self.assertEqual(refused.code, "question_not_approved")  # type: ignore[union-attr]
        self._assert_absent(paper_id)

    def test_multi_item_rejects_answer_not_approved(self) -> None:
        paper_id = "paper-d4-e2"
        self.approvals.put(_snapshot("q-d4-e2a", "a-d4-e2a"))  # type: ignore[attr-defined]
        self.approvals.put(_snapshot("q-d4-e2b", "a-d4-e2b", question_approved=True, answer_approved=False))  # type: ignore[attr-defined]
        refused = self._compose(
            paper_id,
            (
                _item(paper_id, 1, "q-d4-e2a", "a-d4-e2a"),
                _item(paper_id, 2, "q-d4-e2b", "a-d4-e2b"),
            ),
        )
        self.assertEqual(refused.code, "answer_not_approved")  # type: ignore[union-attr]
        self._assert_absent(paper_id)

    def test_multi_item_rejects_non_applicable_answer(self) -> None:
        paper_id = "paper-d4-e3"
        self.approvals.put(_snapshot("q-d4-e3a", "a-d4-e3a"))  # type: ignore[attr-defined]
        self.approvals.put(_snapshot("q-d4-e3b", "a-d4-e3b"))  # type: ignore[attr-defined]
        refused = self._compose(
            paper_id,
            (
                _item(paper_id, 1, "q-d4-e3a", "a-d4-e3a"),
                _item(paper_id, 2, "q-d4-e3b", "a-d4-other"),
            ),
        )
        self.assertEqual(refused.code, "answer_not_applicable")  # type: ignore[union-attr]
        self._assert_absent(paper_id)

    def test_multi_item_set_items_is_idempotent_and_replaces(self) -> None:
        paper = _bare_paper("paper-d4-f")
        self.practice.add_paper(paper)  # type: ignore[attr-defined]
        first = (
            _item(paper.paper_id, 1, "q-a", "a-a"),
            _item(paper.paper_id, 2, "q-b", "a-b"),
            _item(paper.paper_id, 3, "q-c", "a-c"),
        )
        self.items.set_items(paper.paper_id, first)  # type: ignore[attr-defined]
        self.assertEqual(self.items.items_of(paper.paper_id), first)  # type: ignore[attr-defined]
        self.items.set_items(paper.paper_id, first)  # type: ignore[attr-defined]
        self.assertEqual(self.items.items_of(paper.paper_id), first)  # type: ignore[attr-defined]
        second = (
            _item(paper.paper_id, 1, "q-d", "a-d"),
            _item(paper.paper_id, 2, "q-e", "a-e"),
        )
        self.items.set_items(paper.paper_id, second)  # type: ignore[attr-defined]
        self.assertEqual(self.items.items_of(paper.paper_id), second)  # type: ignore[attr-defined]

    def test_single_item_paper_remains_intact_after_multi_feature_landed(self) -> None:
        self.approvals.put(_snapshot("q-d4-g", "a-d4-g", item_order=("sq-1",)))  # type: ignore[attr-defined]
        self._activate("q-d4-g", "a-d4-g")
        opened = open_paper(
            _command("q-d4-g"),
            self.approvals,  # type: ignore[arg-type]
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.files,
            self.renderer,
            self.logger,
            "req-d4-g",
            lambda: "paper-d4-g",
            actor_teacher_id=_TEACHER,
            attempt_text="5",
            publications=self.publications,  # type: ignore[attr-defined]
        )
        self.assertIsInstance(opened, Ok)  # type: ignore[attr-defined]
        view = opened.value  # type: ignore[union-attr]
        self.assertIsNone(view.render_code)
        self.assertEqual(view.paper.status, "可打印")
        self.assertEqual(self.items.items_of(view.paper.paper_id), ())  # type: ignore[attr-defined]
        resolved = _resolve_items(view.paper.paper_id, self.practice, self.items)  # type: ignore[arg-type]
        self.assertEqual(resolved[0].question_version_id, view.paper.question_version_id)
        self.assertEqual(resolved[0].order_no, 1)
        confirmed = confirm_attempt(
            ConfirmCommand(
                operation_key="op-d4-g",
                paper_id=view.paper.paper_id,
                sub_question_id="sq-1",
                teacher_id=_TEACHER,
                review_version_id=view.paper.review_version_id,
                decision="adopt",
                fixture_answer_id=view.fixture_answer_id,
            ),
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.logger,
            "req-d4-g-confirm",
            lambda: "conf-d4-g",
            actor_teacher_id=_TEACHER,
        )
        self.assertIsInstance(confirmed, Ok)  # type: ignore[attr-defined]
        self.assertEqual(confirmed.value.decision, "adopt")  # type: ignore[union-attr]
        self.assertEqual(self.items.items_of(view.paper.paper_id), ())  # type: ignore[attr-defined]

    def test_multi_item_rejects_duplicate_or_nonpositive_order_no(self) -> None:
        samples = (
            ("paper-d4-h0", (_item("paper-d4-h0", 0, "q-h", "a-h"), _item("paper-d4-h0", 2, "q-h2", "a-h2"))),
            ("paper-d4-hn", (_item("paper-d4-hn", -1, "q-h", "a-h"), _item("paper-d4-hn", 2, "q-h2", "a-h2"))),
            ("paper-d4-hd", (_item("paper-d4-hd", 1, "q-h", "a-h"), _item("paper-d4-hd", 1, "q-h2", "a-h2"))),
        )
        for paper_id, given in samples:
            refused = self._compose(paper_id, given)
            self.assertIsInstance(refused, Err)  # type: ignore[attr-defined]
            self.assertEqual(refused.code, "bad_order")  # type: ignore[union-attr]
            self._assert_absent(paper_id)

    def test_multi_item_rejects_item_without_active_publication(self) -> None:
        paper_id = "paper-d5-g"
        self.approvals.put(_snapshot("q-d5-g1", "a-d5-g1"))  # type: ignore[attr-defined]
        self.approvals.put(_snapshot("q-d5-g2", "a-d5-g2"))  # type: ignore[attr-defined]
        refused = self._compose(
            paper_id,
            (
                _item(paper_id, 1, "q-d5-g1", "a-d5-g1"),
                _item(paper_id, 2, "q-d5-g2", "a-d5-g2"),
            ),
        )
        self.assertIsInstance(refused, Err)  # type: ignore[attr-defined]
        self.assertEqual(refused.code, "no_active_publication")  # type: ignore[union-attr]
        self._assert_absent(paper_id)

    def test_retire_does_not_affect_existing_papers(self) -> None:
        paper_id = "paper-d6-b4"
        self.approvals.put(_snapshot("q-d6-b4a", "a-d6-b4a", item_order=("sq-1",)))  # type: ignore[attr-defined]
        self.approvals.put(_snapshot("q-d6-b4b", "a-d6-b4b", item_order=("sq-2",)))  # type: ignore[attr-defined]
        self._activate("q-d6-b4a", "a-d6-b4a")
        self._activate("q-d6-b4b", "a-d6-b4b")
        composed = self._compose(
            paper_id,
            (
                _item(paper_id, 1, "q-d6-b4a", "a-d6-b4a"),
                _item(paper_id, 2, "q-d6-b4b", "a-d6-b4b"),
            ),
        )
        self.assertIsInstance(composed, Ok)  # type: ignore[attr-defined]
        assert isinstance(composed, Ok)
        frozen_question = composed.value.question_version_id
        frozen_answer = composed.value.answer_version_id
        code = retire_publication(
            self.publications,  # type: ignore[arg-type]
            "q-d6-b4a",
            "a-d6-b4a",
            _TEACHER,
            self.logger,
            request_id="req-d6-b4",
        )
        self.assertEqual(code, "retired")  # type: ignore[attr-defined]
        drawn = render_paper(
            paper_id,
            self.approvals,  # type: ignore[arg-type]
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.files,
            self.renderer,
            self.logger,
            "req-d6-b4-render",
            actor_teacher_id=_TEACHER,
            items=self.items,  # type: ignore[arg-type]
        )
        self.assertIsInstance(drawn, Ok)  # type: ignore[attr-defined]
        assert isinstance(drawn, Ok)
        self.practice.put_answer(  # type: ignore[attr-defined]
            PendingAnswer(
                fixture_answer_id="fix-d6-b4",
                paper_id=paper_id,
                sub_question_id="sq-1",
                review_version_id=composed.value.review_version_id,
                student_id=_STUDENT,
                status="pending",
                answer_text="2",
            )
        )
        confirmed = confirm_attempt(
            ConfirmCommand(
                operation_key="op-d6-b4",
                paper_id=paper_id,
                sub_question_id="sq-1",
                teacher_id=_TEACHER,
                review_version_id=composed.value.review_version_id,
                decision="adopt",
                fixture_answer_id="fix-d6-b4",
            ),
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.logger,
            "req-d6-b4-confirm",
            lambda: "conf-d6-b4",
            actor_teacher_id=_TEACHER,
        )
        self.assertIsInstance(confirmed, Ok)  # type: ignore[attr-defined]
        stored = self.practice.get_paper(paper_id)  # type: ignore[attr-defined]
        assert stored is not None
        self.assertEqual(stored.question_version_id, frozen_question)  # type: ignore[attr-defined]
        self.assertEqual(stored.answer_version_id, frozen_answer)  # type: ignore[attr-defined]
        self.assertEqual(drawn.value.question_version_id, frozen_question)  # type: ignore[attr-defined]
        self.assertEqual(drawn.value.answer_version_id, frozen_answer)  # type: ignore[attr-defined]
        self.assertIsNone(self.publications.active_of("q-d6-b4a", "a-d6-b4a"))  # type: ignore[attr-defined]

    def test_single_item_rejects_without_active_publication(self) -> None:
        self.approvals.put(_snapshot("q-d5-h", "a-d5-h"))  # type: ignore[attr-defined]
        refused = issue_paper(
            _command("q-d5-h"),
            self.approvals,  # type: ignore[arg-type]
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.logger,
            "req-d5-h",
            lambda: "paper-d5-h",
            actor_teacher_id=_TEACHER,
            publications=self.publications,  # type: ignore[attr-defined]
        )
        self.assertIsInstance(refused, Err)  # type: ignore[attr-defined]
        self.assertEqual(refused.code, "no_active_publication")  # type: ignore[union-attr]
        self.assertIsNone(self.practice.get_paper("paper-d5-h"))  # type: ignore[attr-defined]
        self.assertTrue(
            any(event.outcome == "no_active_publication" for event in self.logger.events)
        )  # type: ignore[attr-defined]

    def test_open_paper_rejects_without_active_publication(self) -> None:
        self.approvals.put(_snapshot("q-d5-i", "a-d5-i", item_order=("sq-1",)))  # type: ignore[attr-defined]
        self.assertIsNone(self.publications.active_of("q-d5-i", "a-d5-i"))  # type: ignore[attr-defined]
        refused = open_paper(
            _command("q-d5-i"),
            self.approvals,  # type: ignore[arg-type]
            self.auth,
            self.practice,  # type: ignore[arg-type]
            self.files,
            self.renderer,
            self.logger,
            "req-d5-i",
            lambda: "paper-d5-i",
            actor_teacher_id=_TEACHER,
            attempt_text="5",
            publications=self.publications,  # type: ignore[attr-defined]
        )
        self.assertIsInstance(refused, Err)  # type: ignore[attr-defined]
        self.assertEqual(refused.code, "no_active_publication")  # type: ignore[union-attr]
        self.assertIsNone(self.practice.get_paper("paper-d5-i"))  # type: ignore[attr-defined]

    def _activate(self, question_version_id: str, answer_version_id: str) -> None:
        self.publications.put(  # type: ignore[attr-defined]
            Publication(
                publication_id=f"pub-{question_version_id}-{answer_version_id}",
                question_version_id=question_version_id,
                answer_version_id=answer_version_id,
                subject_id=_SUBJECT,
                status="active",
            )
        )

    def _compose(self, paper_id: str, items: tuple[PracticeItem, ...]) -> Ok[Paper] | Err:
        return compose_multi_item_paper(
            paper_id,
            items,
            teacher_id=_TEACHER,
            student_id=_STUDENT,
            review_version_id="rev-d4",
            approvals=self.approvals,  # type: ignore[arg-type]
            publications=self.publications,  # type: ignore[attr-defined]
            writer=self.writer,  # type: ignore[arg-type]
        )

    def _assert_absent(self, paper_id: str) -> None:
        self.assertIsNone(self.practice.get_paper(paper_id))  # type: ignore[attr-defined]
        self.assertEqual(self.items.items_of(paper_id), ())  # type: ignore[attr-defined]
        self._assert_page_count(paper_id, 0)

    def _assert_pages(self, paper_id: str, given: tuple[PracticeItem, ...]) -> None:
        self._assert_page_count(paper_id, len(given))
        pool = getattr(self, "pool", None)
        if pool is None:
            return
        first_page = _text(
            pool,
            "SELECT question_version_id FROM paper_pages WHERE paper_id = %s AND page_number = 1",
            (paper_id,),
        )
        self.assertEqual(first_page, given[0].question_version_id)  # type: ignore[attr-defined]
        score = _text(
            pool,
            "SELECT score::text FROM practice_item WHERE paper_id = %s ORDER BY order_no LIMIT 1",
            (paper_id,),
        )
        self.assertEqual(score, None)  # type: ignore[attr-defined]

    def _assert_page_count(self, paper_id: str, expected: int) -> None:
        pool = getattr(self, "pool", None)
        if pool is None:
            return
        count = _scalar(pool, "SELECT count(*) FROM paper_pages WHERE paper_id = %s", (paper_id,))
        self.assertEqual(count, expected)  # type: ignore[attr-defined]


class MemoryPracticeItemTest(PracticeItemCases, unittest.TestCase):
    def setUp(self) -> None:
        self.approvals = MemoryApprovals()
        self.publications = MemoryPublications()
        self.practice = MemoryPractice()
        self.items = MemoryPracticeItems()
        self.writer = MemoryComposedWriter(self.practice, self.items)
        self.auth = MemoryAuth()
        self.auth.grant(_TEACHER, _STUDENT, _SUBJECT)
        self.files = MemoryFiles()
        self.renderer = StdPdf()
        self.logger = _Log()


class PgPracticeItemTest(PracticeItemCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_approvals import PgApprovals
        from backend.catalog.adapters.pg_publications import PgPublications
        from backend.practice.adapters.pg_items import PgPracticeItems
        from backend.practice.adapters.pg_practice import PgPractice

        self.pool = _pool()
        _truncate(self.pool)
        self.approvals = PgApprovals(self.pool)
        self.publications = PgPublications(self.pool)
        self.practice = PgPractice(self.pool)
        self.items = PgPracticeItems(self.pool)
        self.writer = self.items
        self.auth = MemoryAuth()
        self.auth.grant(_TEACHER, _STUDENT, _SUBJECT)
        self.files = MemoryFiles()
        self.renderer = StdPdf()
        self.logger = _Log()


def _snapshot(
    question_version_id: str,
    answer_version_id: str,
    *,
    question_approved: bool = True,
    answer_approved: bool = True,
    item_order: tuple[str, ...] = (),
) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=question_version_id,
        answer_version_id=answer_version_id,
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        question_approved=question_approved,
        answer_approved=answer_approved,
        retired=False,
        subject_id=_SUBJECT,
        item_order=item_order,
        stem=_STEM,
        answer_text="2",
    )


def _item(paper_id: str, order_no: int, question_version_id: str, answer_version_id: str) -> PracticeItem:
    return PracticeItem(
        paper_id=paper_id,
        order_no=order_no,
        question_version_id=question_version_id,
        answer_version_id=answer_version_id,
        score=None,
    )


def _command(question_version_id: str) -> IssuePaperCommand:
    return IssuePaperCommand(
        teacher_id=_TEACHER,
        student_id=_STUDENT,
        subject_id=_SUBJECT,
        question_version_id=question_version_id,
        review_version_id="rev-d4",
    )


def _bare_paper(paper_id: str) -> Paper:
    return Paper(
        paper_id=paper_id,
        teacher_id=_TEACHER,
        student_id=_STUDENT,
        subject_id=_SUBJECT,
        question_version_id="q-old",
        answer_version_id="a-old",
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        review_version_id="rev-d4",
        file_id=None,
        status="待渲染",
        item_order=("sq-1",),
        file_checksum=None,
        formula="(-3)+5",
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


def _truncate(pool: object) -> None:
    statement = """
        TRUNCATE TABLE
            publication, practice_item, confirmations, attempts, paper_pages, papers, approvals
        RESTART IDENTITY CASCADE
    """
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement)


def _scalar(pool: object, statement: str, params: tuple[object, ...]) -> int:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        row = conn.execute(statement, params).fetchone()
    return int(row[0])


def _text(pool: object, statement: str, params: tuple[object, ...]) -> str | None:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        row = conn.execute(statement, params).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])
