"""Three directories, lesson assignment, and answer text. Memory always runs.

PostgreSQL runs when K12_PG_DSN is set. Keys stay on the synth-r4f prefix.
"""

from __future__ import annotations

import os
import unittest

from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.adapters.memory_books import MemoryBooks
from backend.catalog.application.import_book import import_book
from backend.catalog.domain.book_key import namespaced_key
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.practice.adapters.memory import MemoryPractice
from backend.practice.domain.paper import Paper

_HINT = "在核对页把这一页切到参考答案页再保存"
_BOOK = "synth-r4f-%"


class _Log:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class VolumeCases:
    questions: object
    answers: object
    approvals: object
    books: object
    log: _Log

    def call(
        self,
        book_id: str,
        pages: list[object],
        pairing: list[object] | None = None,
        *,
        toc: object = None,
        toc_page_offset: int = 0,
        dry_run: bool = False,
        unknown_fields: bool = False,
    ) -> object:
        return import_book(
            book_id,
            "math",
            pages,
            [] if pairing is None else pairing,
            self.questions,  # type: ignore[arg-type]
            self.answers,  # type: ignore[arg-type]
            self.approvals,  # type: ignore[arg-type]
            self.log,
            "req-synth-r4f",
            dry_run=dry_run,
            unknown_fields=unknown_fields,
            actor_user_id="actor-synth",
            toc=toc,
            toc_page_offset=toc_page_offset,
            books=self.books,
        )

    def test_both_volumes_may_use_page_one_and_pairs_stay_in_their_volume(self) -> None:
        question = _vol(_qpage(1, "1:1", "synth-q", None), "questions")
        answer = _vol(_apage(1, "1:1", "synth-a"), "answers")
        report = self.call(
            "synth-r4f-both",
            [question, answer],
            [{"answer_page": 1, "question_page": 1}],
        )
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.staged, 1)  # type: ignore[attr-defined]
        self.assertFalse(any(page.reason == "duplicate_page" for page in report.pages))  # type: ignore[attr-defined]
        stored = self.approvals.read_snapshot(report.questions[0].question_version_id)  # type: ignore[attr-defined]
        self.assertEqual(stored.answer_text, "synth-a")
        self.assertEqual(stored.book_id, "synth-r4f-both")
        self.assertEqual(stored.pdf_page, 1)
        self.assertTrue(self.books.has_book("synth-r4f-both"))  # type: ignore[attr-defined]

    def test_a_repeated_page_inside_one_volume_is_still_duplicate_page(self) -> None:
        pages = [
            _vol(_qpage(1, "1:1", "synth-a", "a"), "questions"),
            _vol(_qpage(1, "1:2", "synth-b", "b"), "questions"),
        ]
        report = self.call("synth-r4f-dup", pages)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertTrue(all(page.reason == "duplicate_page" for page in report.pages))  # type: ignore[attr-defined]
        self.assertFalse(self.books.has_book("synth-r4f-dup"))  # type: ignore[attr-defined]

    def test_an_unmarked_answer_page_refuses_the_book(self) -> None:
        pages = [
            _vol(_qpage(1, "1:1", "synth-q", "synth-a"), "questions"),
            {
                "pdf_page": 2,
                "role": "answers",
                "volume": "answers",
                "questions": None,
                "answers": [],
                "has_question_file": True,
            },
        ]
        report = self.call("synth-r4f-mark", pages)
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        marked = next(page for page in report.pages if page.pdf_page == 2)  # type: ignore[attr-defined]
        self.assertEqual(marked.reason, "answer_page_not_marked")
        self.assertEqual(marked.hint, _HINT)
        self.assertFalse(self.books.has_book("synth-r4f-mark"))  # type: ignore[attr-defined]
        self.assertIsNone(self.approvals.read_snapshot("qv-synth-r4f-mark.p0001-1-1"))  # type: ignore[attr-defined]

    def test_an_answer_volume_without_pairs_is_unpaired(self) -> None:
        pages = [
            _vol(_qpage(1, "1:1", "synth-q", None), "questions"),
            _vol(_apage(1, "1:1", "synth-a"), "answers"),
        ]
        report = self.call("synth-r4f-loose", pages, [])
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertIn("unpaired_answer", [page.reason for page in report.pages])  # type: ignore[attr-defined]

    def test_the_old_layout_still_imports_and_an_unknown_field_is_rejected(self) -> None:
        report = self.call("synth-r4f-old", [_qpage(1, "1:1", "synth-old", "synth-a")])
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.staged, 1)  # type: ignore[attr-defined]
        self.assertEqual(report.pages[0].volume, "")  # type: ignore[attr-defined]
        extra = _qpage(1, "1:1", "synth-extra", "synth-a")
        extra["note"] = "x"
        refused = self.call("synth-r4f-unk", [extra])
        self.assertEqual(refused.reason, "unknown_field")  # type: ignore[attr-defined]
        self.assertFalse(refused.written)  # type: ignore[attr-defined]
        flagged = self.call("synth-r4f-flag", [_qpage(1, "1:1", "synth-flag", "a")], unknown_fields=True)
        self.assertEqual(flagged.reason, "unknown_field")  # type: ignore[attr-defined]

    def test_a_question_lands_in_the_lesson_that_covers_its_page(self) -> None:
        pages = [
            _vol(_qpage(1, "1:1", "synth-early", "synth-a"), "questions"),
            _vol(_qpage(10, "1:1", "synth-late", None), "questions"),
        ]
        report = self.call("synth-r4f-span", pages, toc=_toc(_SPAN))
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.toc_chapters, 1)  # type: ignore[attr-defined]
        self.assertEqual(report.toc_sections, 1)  # type: ignore[attr-defined]
        self.assertEqual(report.toc_lessons, 4)  # type: ignore[attr-defined]
        self.assertEqual(report.toc_unparsed, ((1, 10),))  # type: ignore[attr-defined]
        self.assertFalse(report.toc_changed)  # type: ignore[attr-defined]
        orders = {row.original_key + "@" + str(row.lesson_order): row.lesson_order for row in report.questions}  # type: ignore[attr-defined]
        by_stem = {row.question_version_id: row.lesson_order for row in report.questions}  # type: ignore[attr-defined]
        early = next(row for row in report.questions if row.question_version_id.endswith("p0001-1-1"))  # type: ignore[attr-defined]
        late = next(row for row in report.questions if row.question_version_id.endswith("p0010-1-1"))  # type: ignore[attr-defined]
        self.assertEqual(early.lesson_order, 1)
        self.assertEqual(late.lesson_order, 4)
        self.assertEqual(len(orders), 2)
        self.assertEqual(len(by_stem), 2)
        self.assertEqual(len(self.books.lessons_of("synth-r4f-span")), 4)  # type: ignore[attr-defined]

    def test_a_page_before_the_first_lesson_stays_unassigned(self) -> None:
        page = _vol(_qpage(1, "1:1", "synth-before", "synth-a"), "questions")
        report = self.call("synth-r4f-none", [page], toc=_toc("## 一、synth-ch\nsynth-later \u2026 4\n"))
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertIsNone(report.questions[0].lesson_order)  # type: ignore[attr-defined]
        self.assertEqual(self.books.lessons_of("synth-r4f-none")[0].start_page, 4)  # type: ignore[attr-defined]

    def test_offset_moves_the_lesson_and_a_dry_run_writes_nothing(self) -> None:
        page = _vol(_qpage(1, "1:1", "synth-shift", "synth-a"), "questions")
        report = self.call(
            "synth-r4f-off",
            [page],
            toc=_toc("## 一、synth-ch\nsynth-les \u2026 1\n"),
            toc_page_offset=2,
            dry_run=True,
        )
        self.assertFalse(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.toc_lessons, 1)  # type: ignore[attr-defined]
        self.assertIsNone(report.questions[0].lesson_order)  # type: ignore[attr-defined]
        self.assertFalse(self.books.has_book("synth-r4f-off"))  # type: ignore[attr-defined]

    def test_a_changed_catalog_replaces_lessons_and_leaves_the_question_and_the_paper(self) -> None:
        page = _vol(_qpage(1, "1:1", "synth-hold", "synth-a"), "questions")
        first = self.call("synth-r4f-toc", [page], toc=_toc("## 一、synth-ch\nsynth-les (1) \u2026 1\n"))
        self.assertTrue(first.written)  # type: ignore[attr-defined]
        self.assertFalse(first.toc_changed)  # type: ignore[attr-defined]
        stored = self.approvals.read_snapshot(first.questions[0].question_version_id)  # type: ignore[attr-defined]
        self._place_paper(stored)
        folded = self.call("synth-r4f-toc", [page], toc=_toc("## 一、synth-ch\nsynth-les（1） \u2026 1\n"))
        self.assertTrue(folded.written)  # type: ignore[attr-defined]
        self.assertFalse(folded.toc_changed)  # type: ignore[attr-defined]
        self.assertEqual(folded.kept, 1)  # type: ignore[attr-defined]
        changed = self.call("synth-r4f-toc", [page], toc=_toc("## 一、synth-ch\nsynth-other \u2026 1\n"))
        self.assertTrue(changed.toc_changed)  # type: ignore[attr-defined]
        self.assertEqual(changed.kept, 1)  # type: ignore[attr-defined]
        again = self.approvals.read_snapshot(stored.question_version_id)  # type: ignore[attr-defined]
        self.assertEqual(again.stem, "synth-hold")
        self.assertEqual(again.answer_text, "synth-a")
        self.assertEqual(again.question_version_id, stored.question_version_id)
        self.assertEqual(self.books.lessons_of("synth-r4f-toc")[0].lesson_title, "synth-other")  # type: ignore[attr-defined]
        self.assertEqual(self._paper_mark(), (stored.question_version_id, "synth-formula"))
        omitted = self.call("synth-r4f-toc", [page])
        self.assertFalse(omitted.toc_changed)  # type: ignore[attr-defined]
        self.assertEqual(self.books.lessons_of("synth-r4f-toc")[0].lesson_title, "synth-other")  # type: ignore[attr-defined]

    def test_parts_join_into_answer_text_and_content_only_stays_kept(self) -> None:
        page = _vol(_qpage(1, "1:1", "synth-stem", None), "questions")
        page["answers"] = [_parts_answer()]
        report = self.call("synth-r4f-parts", [page])
        self.assertEqual(report.staged, 1)  # type: ignore[attr-defined]
        stored = self.approvals.read_snapshot(report.questions[0].question_version_id)  # type: ignore[attr-defined]
        self.assertEqual(stored.answer_text, "(1) synth-a synth-step；(2) synth-b")
        again = self.call("synth-r4f-parts", [page])
        self.assertEqual(again.kept, 1)  # type: ignore[attr-defined]
        plain = [_qpage(1, "1:1", "synth-stem", "synth-only")]
        first = self.call("synth-r4f-plain", plain)
        second = self.call("synth-r4f-plain", plain)
        self.assertEqual(second.kept, 1)  # type: ignore[attr-defined]
        left = self.approvals.read_snapshot(first.questions[0].question_version_id)  # type: ignore[attr-defined]
        self.assertEqual(left.answer_text, "synth-only")
        conflict_page = _qpage(1, "1:1", "synth-stem", None)
        conflict_page["answers"] = [_parts_answer()]
        conflict = self.call("synth-r4f-plain", [conflict_page])
        self.assertFalse(conflict.written)  # type: ignore[attr-defined]
        self.assertEqual(conflict.conflict, 1)  # type: ignore[attr-defined]
        held = self.approvals.read_snapshot(left.question_version_id)  # type: ignore[attr-defined]
        self.assertEqual(held.answer_text, "synth-only")

    def test_an_old_row_is_not_backfilled_with_book_or_page(self) -> None:
        key = namespaced_key("synth-r4f-keep", 1, "1:1")
        answer_key = namespaced_key("synth-r4f-keep", 1, "1:1:ocr:1")
        self.approvals.insert_if_absent(  # type: ignore[attr-defined]
            ApprovalSnapshot(
                question_version_id="qv-" + key.replace(":", "-"),
                answer_version_id="av-" + answer_key.replace(":", "-"),
                asset_ids=(),
                layout_template_id="",
                question_approved=False,
                answer_approved=False,
                retired=False,
                subject_id="math",
                stem="synth-keep",
                answer_text="synth-a",
                type="single_choice",
                structure="choice",
                options=("A. 2",),
            )
        )
        report = self.call("synth-r4f-keep", [_qpage(1, "1:1", "synth-keep", "synth-a")])
        self.assertEqual(report.kept, 1)  # type: ignore[attr-defined]
        stored = self.approvals.read_snapshot("qv-" + key.replace(":", "-"))  # type: ignore[attr-defined]
        self.assertIsNone(stored.book_id)
        self.assertIsNone(stored.pdf_page)

    def test_textcircled_is_a_known_command(self) -> None:
        question = _question("1:1", "1", "synth")
        question["stem"] = [{"type": "math", "latex": r"\textcircled{1}"}]
        page = _page(1, "questions", _file(1, [question]), [_answer("1:1", 1, "synth-a")])
        report = self.call("synth-r4f-circ", [page])
        self.assertTrue(report.written)  # type: ignore[attr-defined]
        self.assertEqual(report.questions[0].reason, "")  # type: ignore[attr-defined]

    def _place_paper(self, snapshot: ApprovalSnapshot) -> None:
        raise NotImplementedError

    def _paper_mark(self) -> tuple[str, str]:
        raise NotImplementedError


class MemoryVolumeTest(VolumeCases, unittest.TestCase):
    def setUp(self) -> None:
        self.questions = MemoryDrafts()
        self.answers = MemoryAnswers()
        self.approvals = MemoryApprovals()
        self.books = MemoryBooks()
        self.practice = MemoryPractice()
        self.log = _Log()
        self.paper_id = ""

    def _place_paper(self, snapshot: ApprovalSnapshot) -> None:
        self.paper_id = "paper-synth-r4f-toc"
        self.practice.place_paper(
            Paper(
                paper_id=self.paper_id,
                teacher_id="teacher-synth",
                student_id="student-synth",
                subject_id="math",
                question_version_id=snapshot.question_version_id,
                answer_version_id=snapshot.answer_version_id,
                asset_ids=(),
                layout_template_id="slots",
                review_version_id="rev-synth",
                file_id=None,
                status="可打印",
                item_order=(snapshot.question_version_id,),
                formula="synth-formula",
            )
        )

    def _paper_mark(self) -> tuple[str, str]:
        paper = self.practice.get_paper(self.paper_id)
        assert paper is not None
        return paper.question_version_id, paper.formula


class PgVolumeTest(VolumeCases, unittest.TestCase):
    def setUp(self) -> None:
        self.pool = None
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_answers import PgAnswers
        from backend.catalog.adapters.pg_approvals import PgApprovals
        from backend.catalog.adapters.pg_books import PgBooks
        from backend.catalog.adapters.pg_questions import PgQuestions

        self.pool = _pool()
        _wipe(self.pool)
        self.questions = PgQuestions(self.pool)
        self.answers = PgAnswers(self.pool)
        self.approvals = PgApprovals(self.pool)
        self.books = PgBooks(self.pool)
        self.log = _Log()

    def tearDown(self) -> None:
        if self.pool is not None:
            _wipe(self.pool)

    def _place_paper(self, snapshot: ApprovalSnapshot) -> None:
        assert self.pool is not None
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO papers (
                        paper_id, teacher_id, student_id, subject_id, question_version_id,
                        answer_version_id, asset_ids, layout_template_id, review_version_id,
                        status, item_order, formula
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "paper-synth-r4f-toc",
                        "teacher-synth",
                        "student-synth",
                        "math",
                        snapshot.question_version_id,
                        snapshot.answer_version_id,
                        [],
                        "slots",
                        "rev-synth",
                        "可打印",
                        [snapshot.question_version_id],
                        "synth-formula",
                    ),
                )

    def _paper_mark(self) -> tuple[str, str]:
        assert self.pool is not None
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT question_version_id, formula, item_order
                FROM papers WHERE paper_id = %s
                """,
                ("paper-synth-r4f-toc",),
            ).fetchone()
        self.assertEqual(list(row[2]), [row[0]])
        return str(row[0]), str(row[1])


_SPAN = "\n".join(
    [
        "# 目录",
        "",
        "## 一、synth-ch",
        "synth-sec",
        "synth-les (1) \u2026\u2026 1",
        "synth-dots ... 4",
        "synth-one \u2026 6",
        "synth-run .... 8",
        "参考答案 \u2026\u2026 9",
        "?? 3",
    ]
)


def _toc(text: str) -> list[dict[str, object]]:
    return [{"pdf_page": 1, "text": text}]


def _vol(page: dict[str, object], volume: str) -> dict[str, object]:
    page["volume"] = volume
    if volume == "questions":
        page["answers"] = [] if page.get("answers") is None else page["answers"]
    return page


def _parts_answer() -> dict[str, object]:
    answer = _answer("1:1", 1, "")
    answer["content"] = []
    answer["parts"] = [
        {"sub_key": "1", "role": "result", "order": 1, "content": [{"type": "text", "value": "synth-a"}]},
        {"sub_key": "1", "role": "step", "order": 2, "content": [{"type": "text", "value": "synth-step"}]},
        {"sub_key": "2", "role": "result", "order": 3, "content": [{"type": "text", "value": "synth-b"}]},
    ]
    return answer


def _qpage(page: int, key: str, stem: str, answer: str | None) -> dict[str, object]:
    answers = [] if answer is None else [_answer(key, page, answer)]
    number = key.split(":")[-1]
    return _page(page, "questions", _file(page, [_question(key, number, stem)]), answers)


def _apage(page: int, key: str, text: str) -> dict[str, object]:
    return _page(page, "answers", None, [_answer(key, page, text)])


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


def _wipe(pool: object) -> None:
    statements = [
        "DELETE FROM teacher_decision WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM ai_suggestion WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM intake_page WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM practice_item_box WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM practice_item WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM confirmations WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM attempts WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM paper_pages WHERE paper_id LIKE 'paper-synth-r4f%'",
        "DELETE FROM papers WHERE paper_id LIKE 'paper-synth-r4f%' OR question_version_id LIKE 'qv-synth-r4f-%'",
        (
            "DELETE FROM answer_part WHERE answer_id IN "
            "(SELECT answer_id FROM answers WHERE key LIKE %s OR question_key LIKE %s)"
        ),
        (
            "DELETE FROM answer_asset WHERE answer_id IN "
            "(SELECT answer_id FROM answers WHERE key LIKE %s OR question_key LIKE %s)"
        ),
        "DELETE FROM answers WHERE key LIKE %s OR question_key LIKE %s",
        (
            "DELETE FROM question_option WHERE question_id IN "
            "(SELECT question_id FROM questions WHERE key LIKE %s)"
        ),
        (
            "DELETE FROM sub_question WHERE question_id IN (SELECT question_id FROM questions WHERE key LIKE %s)"
        ),
        (
            "DELETE FROM question_asset WHERE question_id IN "
            "(SELECT question_id FROM questions WHERE key LIKE %s)"
        ),
        "DELETE FROM questions WHERE key LIKE %s",
        (
            "DELETE FROM approvals WHERE question_version_id LIKE 'qv-synth-r4f-%' "
            "OR answer_version_id LIKE 'av-synth-r4f-%'"
        ),
        "DELETE FROM book_lesson WHERE book_id LIKE %s",
        "DELETE FROM book WHERE book_id LIKE %s",
    ]
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            for statement in statements:
                if "%s" not in statement:
                    conn.execute(statement)
                    continue
                count = statement.count("%s")
                conn.execute(statement, (_BOOK,) * count)
