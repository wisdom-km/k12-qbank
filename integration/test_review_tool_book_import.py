"""Turn a two-page synthetic markdown book into drafts and import the book.

The pages are not from a textbook. Both pages use the original key 1:1.
"""

from __future__ import annotations

import json
import unittest

from core.answer_contract import to_answer_files
from core.answer_split import split_answers
from core.draft_contract import to_draft_file
from core.split import split_questions
from core.split_rules import compile_rules
from md_json_review import rules_text

from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.import_book import import_book
from backend.kernel.log_event import LogEvent


class _Log:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class ReviewToolBookImportTest(unittest.TestCase):
    def test_two_markdown_pages_import_as_distinct_questions(self) -> None:
        rules = compile_rules(json.loads(rules_text()))
        pages = []
        stems = ("synth甲", "synth乙")
        letters = ("B", "C")
        for pdf_page, stem, letter in zip((1, 2), stems, letters, strict=True):
            question = split_questions(
                f"一. 选择题\n1. {stem}（ ）\nA. 3\nB. 4\nC. 5\nD. 6\n",
                rules,
            )
            self.assertTrue(question["ok"], question.get("reason"))
            self.assertEqual([item["key"] for item in question["questions"]], ["1:1"])
            answer = split_answers(f"一. 选择题\n1. {letter}\n", rules)
            self.assertTrue(answer["ok"], answer.get("reason"))
            files = to_answer_files(answer, pdf_page, ["1:1:ocr:1"])
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["status"], "confirmed")
            self.assertTrue(files[0]["applicable"])
            pages.append(
                {
                    "pdf_page": pdf_page,
                    "role": "questions",
                    "questions": to_draft_file(question, pdf_page),
                    "answers": files,
                }
            )
        drafts = MemoryDrafts()
        bank = MemoryAnswers()
        approvals = MemoryApprovals()
        log = _Log()
        report = import_book(
            "synth-tool",
            "math",
            pages,
            [],
            drafts,
            bank,
            approvals,
            log,
            "req-synth-tool",
            actor_user_id="actor-synth",
        )
        self.assertTrue(report.written)
        self.assertEqual(report.staged, 2)
        self.assertEqual(report.conflict, 0)
        self.assertEqual(
            [row.key for row in report.questions],
            ["synth-tool.p0001:1:1", "synth-tool.p0002:1:1"],
        )
        self.assertIsNone(drafts.read("1:1"))
        first = approvals.read_snapshot("qv-synth-tool.p0001-1-1")
        second = approvals.read_snapshot("qv-synth-tool.p0002-1-1")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertIn("synth甲", first.stem)
        self.assertIn("synth乙", second.stem)
        self.assertNotEqual(first.stem, second.stem)
        text = " ".join(event.outcome for event in log.events)
        self.assertNotIn("synth甲", text)
        self.assertEqual(log.events[-1].event, "import_book")


if __name__ == "__main__":
    unittest.main()
