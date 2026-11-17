"""Install md-json-review, split one synthetic OCR page, and import both drafts.

The page is not from a textbook. A failure prints request_id and code.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.answer_contract import answer_filename, to_answer_files
from core.answer_split import split_answers
from core.draft_contract import to_draft_file
from core.split import split_questions
from core.split_rules import compile_rules
from md_json_review import rules_text

from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.application.import_answer import import_answer_draft
from backend.catalog.application.import_draft import import_question_draft
from backend.catalog.domain.validate import publication_blocked
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok

REQUEST_ID = "synthetic-ocr-import"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


def _page_text(name: str) -> str:
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return document[0][0]["content"]


class ReviewToolImportTest(unittest.TestCase):
    def test_k12_question_draft_and_k12_answer_draft_import(self) -> None:
        rules = compile_rules(json.loads(rules_text()))
        question = to_draft_file(split_questions(_page_text("synthetic-question.json"), rules), 1)
        answers = to_answer_files(
            split_answers(_page_text("synthetic-answer.json"), rules),
            1,
            ["1:1:ocr:1"],
        )
        self.assertEqual(len(answers), 1)
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            question_path = folder / "page.questions.json"
            question_path.write_text(json.dumps(question, ensure_ascii=False), encoding="utf-8")
            answer_dir = folder / "page.answers"
            answer_dir.mkdir()
            answer_path = answer_dir / answer_filename(answers[0]["key"])
            answer_path.write_text(json.dumps(answers[0], ensure_ascii=False), encoding="utf-8")
            question_payload = json.loads(question_path.read_text(encoding="utf-8"))
            answer_payload = json.loads(answer_path.read_text(encoding="utf-8"))

        drafts = MemoryDrafts()
        draft_log = ListLog()
        imported = import_question_draft(question_payload, drafts, draft_log, REQUEST_ID)
        if isinstance(imported, Err):
            print(f"request_id={REQUEST_ID} code={imported.code}", flush=True)
            self.fail(imported.code)
        self.assertIsInstance(imported, Ok)
        self.assertEqual(draft_log.events[-1].outcome, "1")
        self.assertNotIn("2+2", draft_log.events[-1].outcome)
        stored = drafts.read("1:1")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(publication_blocked(stored).code, "draft")

        bank = MemoryAnswers()
        answer_log = ListLog()
        saved = import_answer_draft(answer_payload, bank, answer_log, REQUEST_ID)
        if isinstance(saved, Err):
            print(f"request_id={REQUEST_ID} code={saved.code}", flush=True)
            self.fail(saved.code)
        self.assertIsInstance(saved, Ok)
        self.assertEqual(saved.value.key, "1:1:ocr:1")
        self.assertEqual(answer_log.events[-1].outcome, "1")


if __name__ == "__main__":
    unittest.main()
