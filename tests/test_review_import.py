"""A review folder's draft files import once. An unapproved question cannot be issued."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.import_answer import import_answer_draft
from backend.catalog.application.import_draft import import_question_draft
from backend.catalog.domain.answer import answer_not_publication
from backend.catalog.domain.draft import publication_blocked
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice
from backend.practice.api import IssuePaperCommand
from backend.practice.application.issue_paper import issue_paper

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class ReviewImportTest(unittest.TestCase):
    def test_review_files_import_and_cannot_be_issued(self) -> None:
        questions = json.loads((FIXTURES / "review-page.questions.json").read_text(encoding="utf-8"))
        answer_dir = FIXTURES / "review-page.answers"
        answer_files = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(answer_dir.glob("*.json"))]
        self.assertEqual(len(answer_files), 1)

        logger = ListLog()
        drafts = MemoryDrafts()
        answers = MemoryAnswers()
        imported = import_question_draft(questions, drafts, logger, "req-questions")
        self.assertIsInstance(imported, Ok)
        assert isinstance(imported, Ok)
        self.assertEqual(len(imported.value.questions), 1)
        stored = drafts.read("1:1")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.status, "needs_confirm")
        self.assertEqual(publication_blocked(stored).code, "draft")

        answer = import_answer_draft(answer_files[0], answers, logger, "req-answer")
        self.assertIsInstance(answer, Ok)
        assert isinstance(answer, Ok)
        self.assertEqual(answer.value.question_key, stored.key)
        saved_answer = answers.read("1:1:ocr:1")
        self.assertIsNotNone(saved_answer)
        assert saved_answer is not None
        self.assertEqual(answer_not_publication(saved_answer).code, "draft")
        self.assertEqual(logger.events[-1].outcome, "1")
        self.assertNotIn("计算", logger.events[-1].outcome)

        practice = MemoryPractice()
        issued = issue_paper(
            IssuePaperCommand(
                teacher_id="teacher-synth",
                student_id="student-synth",
                subject_id="math",
                question_version_id=stored.key,
                review_version_id="rev-1",
            ),
            MemoryApprovals(),
            MemoryAuth(),
            practice,
            logger,
            "req-issue",
            actor_teacher_id="teacher-synth",
        )
        self.assertIsInstance(issued, Err)
        assert isinstance(issued, Err)
        self.assertEqual(issued.code, "not_found")
        self.assertEqual(practice.paper_count(), 0)


if __name__ == "__main__":
    unittest.main()
