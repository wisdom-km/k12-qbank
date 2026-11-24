"""Whole-book import. The same original key on two pages stays two questions.

Memory always runs. PostgreSQL runs when K12_PG_DSN is set.
"""

from __future__ import annotations

import os
import unittest

from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.import_book import import_book
from backend.catalog.domain.book_key import namespace_reason, namespaced_key
from backend.catalog.domain.parse import parse_question_draft
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Ok

_A = "synth-r4c-%"
_B = "synth-legacy%"


class _Log:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class BookKeyTest(unittest.TestCase):
    def test_the_same_triple_is_stable_and_different_triples_differ(self) -> None:
        first = namespaced_key("rj-math-7a", 12, "1:1")
        self.assertEqual(first, namespaced_key("rj-math-7a", 12, "1:1"))
        self.assertEqual(first, "rj-math-7a.p0012:1:1")
        self.assertNotEqual(first, namespaced_key("rj-math-7a", 13, "1:1"))
        self.assertNotEqual(first, namespaced_key("rj-math-7b", 12, "1:1"))
        self.assertNotEqual(first, namespaced_key("rj-math-7a", 12, "1:2"))
        self.assertNotEqual(namespaced_key("rj-math-7a", 12, "0:1"), namespaced_key("rj-math-7a", 120, "1"))
        self.assertNotEqual(first, "1:1")
        self.assertEqual(namespace_reason("rj-math-7a", True, "1"), "page_missing")  # type: ignore[arg-type]
        self.assertEqual(namespace_reason("RJ-Math", 1, "1"), "invalid_book_id")

    def test_a_64_character_key_passes_and_a_longer_one_is_not_cut(self) -> None:
        book = "synth-r4c-" + ("a" * 14)
        self.assertEqual(len(book), 24)
        fitting = "b" * 33
        stored = namespaced_key(book, 1, fitting)
        self.assertEqual(len(stored), 64)
        self.assertEqual(namespace_reason(book, 1, fitting), "")
        longer = namespaced_key(book, 1, "b" * 40)
        self.assertGreater(len(longer), 64)
        self.assertEqual(namespace_reason(book, 1, "b" * 40), "key_too_long")
        self.assertEqual(namespace_reason(book, 1, "has space"), "key_too_long")


class BookImportCases:
    questions: object
    answers: object
    approvals: object
    log: _Log

    def rows(self) -> tuple[int, int, int]:
        raise NotImplementedError

    def call(self, book_id: str, pages: list[object], pairing: list[object] | None = None, **kwargs: object) -> object:
        return import_book(
            book_id,
            str(kwargs.get("subject_id", "math")),
            pages,
            [] if pairing is None else pairing,
            self.questions,  # type: ignore[arg-type]
            self.answers,  # type: ignore[arg-type]
            self.approvals,  # type: ignore[arg-type]
            self.log,
            "req-synth",
            dry_run=bool(kwargs.get("dry_run", False)),
            unknown_fields=bool(kwargs.get("unknown_fields", False)),
            actor_user_id="actor-synth",
        )

    def test_two_pages_with_the_same_original_key_stay_distinct(self) -> None:
        report = self.call("synth-r4c-two", [_qpage(1, "1:1", "synth-page-one", "one"), _qpage(2, "1:1", "synth-page-two", "two")])
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.staged, 2)  # type: ignore[attr-defined]
        self.assertEqual(report.conflict, 0)  # type: ignore[attr-defined]
        keys = [row.key for row in report.questions]  # type: ignore[attr-defined]
        self.assertEqual(keys, ["synth-r4c-two.p0001:1:1", "synth-r4c-two.p0002:1:1"])
        first = self.approvals.read_snapshot("qv-synth-r4c-two.p0001-1-1")  # type: ignore[attr-defined]
        second = self.approvals.read_snapshot("qv-synth-r4c-two.p0002-1-1")  # type: ignore[attr-defined]
        self.assertEqual(first.stem, "synth-page-one")
        self.assertEqual(second.stem, "synth-page-two")
        self.assertEqual(first.answer_text, "one")
        self.assertEqual(second.answer_text, "two")
        self.assertIsNone(self.questions.read("1:1"))  # type: ignore[attr-defined]
        text = " ".join(event.outcome for event in self.log.events)
        self.assertNotIn("synth-page-one", text)
        self.assertEqual(self.log.events[-1].event, "import_book")

    def test_sequential_pages_do_not_collide(self) -> None:
        first = self.call("synth-r4c-seq", [_qpage(1, "1:1", "synth-seq-one", "one")])
        second = self.call("synth-r4c-seq", [_qpage(2, "1:1", "synth-seq-two", "two")])
        self.assertEqual(first.staged, 1)  # type: ignore[attr-defined]
        self.assertEqual(second.staged, 1)  # type: ignore[attr-defined]
        self.assertEqual(second.kept, 0)  # type: ignore[attr-defined]
        self.assertIsNotNone(self.approvals.read_snapshot("qv-synth-r4c-seq.p0001-1-1"))  # type: ignore[attr-defined]
        self.assertIsNotNone(self.approvals.read_snapshot("qv-synth-r4c-seq.p0002-1-1"))  # type: ignore[attr-defined]

    def test_back_of_book_pairing_keeps_the_answer_page(self) -> None:
        pages = [
            _qpage(12, "2:1", "synth-q-12", None),
            _apage(101, "2:1", "paired"),
        ]
        report = self.call(
            "synth-r4c-back",
            pages,
            [{"answer_page": 101, "question_page": 12}],
        )
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.questions[0].key, "synth-r4c-back.p0012:2:1")  # type: ignore[attr-defined]
        stored = self.answers.read("synth-r4c-back.p0012:2:1:ocr:1")  # type: ignore[attr-defined]
        self.assertIsNotNone(stored)
        self.assertEqual(stored.pdf_page, 101)
        self.assertEqual(stored.question_key, "synth-r4c-back.p0012:2:1")

    def test_keys_subset_splits_one_answer_page(self) -> None:
        pages = [
            _qpage(12, "2:1", "synth-split-12", None),
            _qpage(13, "2:2", "synth-split-13", None),
            _apage(101, "2:1", "left", "2:2", "right"),
        ]
        report = self.call(
            "synth-r4c-split",
            pages,
            [
                {"answer_page": 101, "question_page": 12, "keys": ["2:1"]},
                {"answer_page": 101, "question_page": 13, "keys": ["2:2"]},
            ],
        )
        self.assertEqual(report.staged, 2)  # type: ignore[attr-defined]
        self.assertEqual(self.answers.read("synth-r4c-split.p0012:2:1:ocr:1").pdf_page, 101)  # type: ignore[attr-defined]
        self.assertEqual(self.answers.read("synth-r4c-split.p0013:2:2:ocr:1").pdf_page, 101)  # type: ignore[attr-defined]

    def test_question_page_answers_default_to_that_page(self) -> None:
        report = self.call("synth-r4c-self", [_qpage(4, "1:1", "synth-self", "here")])
        self.assertEqual(report.staged, 1)  # type: ignore[attr-defined]
        stored = self.answers.read("synth-r4c-self.p0004:1:1:ocr:1")  # type: ignore[attr-defined]
        self.assertEqual(stored.pdf_page, 4)
        self.assertEqual(stored.question_key, "synth-r4c-self.p0004:1:1")

    def test_second_import_is_kept_and_row_counts_stay(self) -> None:
        pages = [_qpage(1, "1:1", "synth-keep", "same")]
        first = self.call("synth-r4c-keep", pages)
        self.assertEqual(first.staged, 1)  # type: ignore[attr-defined]
        before = self.rows()
        again = self.call("synth-r4c-keep", pages)
        self.assertTrue(again.written)  # type: ignore[attr-defined]
        self.assertEqual(again.kept, 1)  # type: ignore[attr-defined]
        self.assertEqual(again.staged, 0)  # type: ignore[attr-defined]
        self.assertEqual(again.conflict, 0)  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_changed_stem_conflicts_and_writes_nothing(self) -> None:
        self.call("synth-r4c-conf", [_qpage(1, "1:1", "synth-original", "ans")])
        before = self.rows()
        report = self.call("synth-r4c-conf", [_qpage(1, "1:1", "synth-changed", "ans")])
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.conflict, 1)  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)
        kept = self.approvals.read_snapshot("qv-synth-r4c-conf.p0001-1-1")  # type: ignore[attr-defined]
        self.assertEqual(kept.stem, "synth-original")

    def test_dry_run_does_not_write(self) -> None:
        before = self.rows()
        report = self.call("synth-r4c-dry", [_qpage(1, "1:1", "synth-dry", "ans")], dry_run=True)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertTrue(report.dry_run)  # type: ignore[attr-defined]
        self.assertEqual(report.staged, 1)  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_page_missing_writes_nothing(self) -> None:
        self._rejects(
            [_page(1, "questions", {"source": {"pdf_page": None}}, [])],
            "page_missing",
        )

    def test_page_mismatch_writes_nothing(self) -> None:
        self._rejects(
            [_page(1, "questions", {"source": {"pdf_page": 9}}, [])],
            "page_mismatch",
        )

    def test_duplicate_page_writes_nothing(self) -> None:
        pages = [_qpage(3, "1:1", "synth-dup-a", "a"), _qpage(3, "1:2", "synth-dup-b", "b")]
        before = self.rows()
        report = self.call("synth-r4c-dup", pages)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual([page.reason for page in report.pages], ["duplicate_page", "duplicate_page"])  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_unpaired_answer_writes_nothing(self) -> None:
        pages = [_qpage(12, "1:1", "synth-unpaired-q", None), _apage(101, "1:1", "loose")]
        self._rejects(pages, "unpaired_answer", book_id="synth-r4c-loose")

    def test_pairing_overlap_writes_nothing(self) -> None:
        pages = [
            _qpage(12, "1:1", "synth-over-12", None),
            _qpage(13, "1:1", "synth-over-13", None),
            _apage(101, "1:1", "twice"),
        ]
        pairing = [
            {"answer_page": 101, "question_page": 12},
            {"answer_page": 101, "question_page": 13},
        ]
        before = self.rows()
        report = self.call("synth-r4c-over", pages, pairing)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertIn("pairing_overlap", [page.reason for page in report.pages])  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_no_question_writes_nothing(self) -> None:
        pages = [_qpage(12, "2:2", "synth-other", None), _apage(101, "1:1", "orphan")]
        before = self.rows()
        report = self.call(
            "synth-r4c-missq",
            pages,
            [{"answer_page": 101, "question_page": 12, "keys": ["1:1"]}],
        )
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertIn("no_question", [page.reason for page in report.pages])  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_too_many_pages_writes_nothing(self) -> None:
        before = self.rows()
        report = self.call("synth-r4c-many", [{"pdf_page": 1, "role": "questions"}] * 601)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.reason, "too_many_pages")  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_unknown_field_writes_nothing(self) -> None:
        before = self.rows()
        report = self.call("synth-r4c-extra", [_qpage(1, "1:1", "synth-extra", "ans")], unknown_fields=True)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.reason, "unknown_field")  # type: ignore[attr-defined]
        nested = dict(_qpage(1, "1:1", "synth-extra", "ans"))
        nested["note"] = "synth-note"
        nested_report = self.call("synth-r4c-extra", [nested])
        self.assertEqual(nested_report.reason, "unknown_field")  # type: ignore[attr-defined]
        self.assertFalse(nested_report.written)  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_invalid_book_id_writes_nothing(self) -> None:
        before = self.rows()
        report = self.call("Bad Book", [_qpage(1, "1:1", "synth-bad", "ans")])
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.reason, "invalid_book_id")  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.log.events[-1].target_id, "")

    def test_key_too_long_writes_nothing(self) -> None:
        book = "synth-r4c-" + ("a" * 14)
        before = self.rows()
        report = self.call(book, [_qpage(1, "b" * 40, "synth-long", None)])
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertIn("key_too_long", [page.reason for page in report.pages])  # type: ignore[attr-defined]
        self.assertEqual(report.questions[0].key, "")  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_a_64_character_key_is_stored(self) -> None:
        book = "synth-r4c-" + ("c" * 14)
        report = self.call(book, [_qpage(1, "b" * 33, "synth-fit", None)])
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.questions[0].outcome, "skipped")  # type: ignore[attr-defined]
        self.assertEqual(len(report.questions[0].key), 64)  # type: ignore[attr-defined]
        self.assertIsNotNone(self.questions.read(report.questions[0].key))  # type: ignore[attr-defined]

    def test_duplicate_answer_key_writes_nothing(self) -> None:
        page = _qpage(1, "1:1", "synth-dup-key", "ans")
        page["answers"] = [page["answers"][0], dict(page["answers"][0])]
        before = self.rows()
        report = self.call("synth-r4c-dankey", [page])
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.pages[0].reason, "duplicate_answer_key")  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)

    def test_legacy_row_stays(self) -> None:
        parsed = parse_question_draft(_file(1, [_question("synth-legacy:1", "1", "legacy-stem")]))
        if not isinstance(parsed, Ok):
            self.fail(parsed.code)  # type: ignore[attr-defined]
        self.questions.save(parsed.value)  # type: ignore[attr-defined]
        self.approvals.put(  # type: ignore[attr-defined]
            ApprovalSnapshot(
                question_version_id="qv-synth-legacy-1",
                answer_version_id="av-synth-legacy-1",
                asset_ids=(),
                layout_template_id="",
                question_approved=False,
                answer_approved=False,
                retired=False,
                subject_id="math",
                stem="legacy-stem",
                answer_text="old",
                type="single_choice",
                structure="choice",
                options=("A. 2",),
            )
        )
        self.call("synth-r4c-new", [_qpage(2, "1:1", "synth-new", "new")])
        legacy = self.questions.read("synth-legacy:1")  # type: ignore[attr-defined]
        self.assertIsNotNone(legacy)
        self.assertEqual(self.approvals.read_snapshot("qv-synth-legacy-1").stem, "legacy-stem")  # type: ignore[attr-defined]
        self.assertIsNotNone(self.questions.read("synth-r4c-new.p0002:1:1"))  # type: ignore[attr-defined]
        self.assertNotEqual("synth-legacy:1", "synth-r4c-new.p0002:1:1")

    def _rejects(self, pages: list[object], reason: str, book_id: str = "synth-r4c-bad") -> None:
        before = self.rows()
        report = self.call(book_id, pages)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        reasons = [page.reason for page in report.pages]  # type: ignore[attr-defined]
        self.assertTrue(report.reason == reason or reason in reasons)  # type: ignore[attr-defined]
        self.assertEqual(self.rows(), before)


class MemoryBookImportTest(BookImportCases, unittest.TestCase):
    def setUp(self) -> None:
        self.questions = MemoryDrafts()
        self.answers = MemoryAnswers()
        self.approvals = MemoryApprovals()
        self.log = _Log()

    def rows(self) -> tuple[int, int, int]:
        return (
            len(self.questions._items),  # type: ignore[attr-defined]
            len(self.answers._items),  # type: ignore[attr-defined]
            len(self.approvals._items),  # type: ignore[attr-defined]
        )


class PgBookImportTest(BookImportCases, unittest.TestCase):
    def setUp(self) -> None:
        self.pool = None
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_answers import PgAnswers
        from backend.catalog.adapters.pg_approvals import PgApprovals
        from backend.catalog.adapters.pg_questions import PgQuestions

        self.pool = _pool()
        _wipe(self.pool)
        self.questions = PgQuestions(self.pool)
        self.answers = PgAnswers(self.pool)
        self.approvals = PgApprovals(self.pool)
        self.log = _Log()

    def tearDown(self) -> None:
        if self.pool is not None:
            _wipe(self.pool)

    def rows(self) -> tuple[int, int, int]:
        return _counts(self.pool)


def _qpage(page: int, key: str, stem: str, answer: str | None) -> dict[str, object]:
    number = key.split(":")[-1]
    answers = [] if answer is None else [_answer(key, page, answer)]
    return _page(page, "questions", _file(page, [_question(key, number, stem)]), answers)


def _apage(page: int, key: str, text: str, second_key: str | None = None, second_text: str | None = None) -> dict[str, object]:
    answers = [_answer(key, page, text)]
    if second_key is not None and second_text is not None:
        answers.append(_answer(second_key, page, second_text))
    return _page(page, "answers", None, answers)


def _page(page: int, role: str, questions: object, answers: list[object]) -> dict[str, object]:
    return {"pdf_page": page, "role": role, "questions": questions, "answers": answers}


def _file(page: int, questions: list[object]) -> dict[str, object]:
    return {
        "contract": "k12-question-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "preface": "",
        "source": {"pdf_page": page},
        "questions": questions,
    }


def _question(key: str, number: str, stem: str) -> dict[str, object]:
    return {
        "key": key,
        "section": "一",
        "number": number,
        "type": "single_choice",
        "structure": "choice",
        "status": "confirmed",
        "stem": [{"type": "text", "value": stem}],
        "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
        "subquestions": [],
        "assets": [],
        "geometry": None,
    }


def _answer(question_key: str, page: int, text: str) -> dict[str, object]:
    return {
        "contract": "k12-answer-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "question_key": question_key,
        "key": question_key + ":ocr:1",
        "origin": "ocr",
        "status": "confirmed",
        "applicable": True,
        "source": {"pdf_page": page},
        "content": [{"type": "text", "value": text}],
        "parts": [],
        "assets": [],
    }


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


def _counts(pool: object) -> tuple[int, int, int]:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        found = []
        for table in ("questions", "answers", "approvals"):
            row = conn.execute("SELECT count(*) FROM " + table).fetchone()
            found.append(int(row[0]))
    return found[0], found[1], found[2]


def _wipe(pool: object) -> None:
    pattern = (_A, _B, _A, _B)
    approval = ("qv-synth-r4c-%", "qv-synth-legacy%", "av-synth-r4c-%", "av-synth-legacy%")
    statements = [
        (
            "DELETE FROM answer_part WHERE answer_id IN "
            "(SELECT answer_id FROM answers WHERE key LIKE %s OR key LIKE %s OR question_key LIKE %s OR question_key LIKE %s)",
            pattern,
        ),
        (
            "DELETE FROM answer_asset WHERE answer_id IN "
            "(SELECT answer_id FROM answers WHERE key LIKE %s OR key LIKE %s OR question_key LIKE %s OR question_key LIKE %s)",
            pattern,
        ),
        (
            "DELETE FROM answers WHERE key LIKE %s OR key LIKE %s OR question_key LIKE %s OR question_key LIKE %s",
            pattern,
        ),
        (
            "DELETE FROM question_option WHERE question_id IN "
            "(SELECT question_id FROM questions WHERE key LIKE %s OR key LIKE %s)",
            (_A, _B),
        ),
        (
            "DELETE FROM sub_question WHERE question_id IN "
            "(SELECT question_id FROM questions WHERE key LIKE %s OR key LIKE %s)",
            (_A, _B),
        ),
        (
            "DELETE FROM question_asset WHERE question_id IN "
            "(SELECT question_id FROM questions WHERE key LIKE %s OR key LIKE %s)",
            (_A, _B),
        ),
        ("DELETE FROM questions WHERE key LIKE %s OR key LIKE %s", (_A, _B)),
        (
            "DELETE FROM approvals WHERE question_version_id LIKE %s OR question_version_id LIKE %s "
            "OR answer_version_id LIKE %s OR answer_version_id LIKE %s",
            approval,
        ),
    ]
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            for statement, params in statements:
                conn.execute(statement, params)
