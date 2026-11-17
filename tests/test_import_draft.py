"""A review draft is stored as itself. It is not published."""

from __future__ import annotations

import unittest

from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.application.import_draft import import_question_draft
from backend.catalog.domain.validate import publication_blocked
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


def draft_file() -> dict:
    return {
        "contract": "k12-question-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "preface": "",
        "source": {"pdf_page": 1},
        "questions": [
            {
                "key": "1:1",
                "section": "一. 选择题",
                "number": "1",
                "type": "single_choice",
                "structure": "choice",
                "status": "confirmed",
                "stem": [{"type": "text", "value": "计算："}, {"type": "math", "latex": "(-3)+5"}],
                "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
                "subquestions": [],
                "assets": [{"role": "crop", "bbox": [0, 0, 10, 20]}],
                "geometry": None,
            }
        ],
    }


class ImportDraftTest(unittest.TestCase):
    def test_review_file_is_stored_without_a_second_shape(self) -> None:
        store = MemoryDrafts()
        logger = ListLog()
        imported = import_question_draft(draft_file(), store, logger, "req-draft")
        self.assertIsInstance(imported, Ok)
        stored = store.read("1:1")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.structure, "choice")
        self.assertEqual(stored.assets[0].bbox, (0.0, 0.0, 10.0, 20.0))
        self.assertIsNone(stored.geometry)
        self.assertEqual(publication_blocked(stored).code, "draft")
        self.assertEqual(logger.events[-1].event, "draft_imported")
        self.assertNotIn("计算", logger.events[-1].outcome)

    def test_page_blocks_are_refused_and_write_nothing(self) -> None:
        store = MemoryDrafts()
        logger = ListLog()
        refused = import_question_draft(
            [[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None}]],
            store,
            logger,
            "req-page",
        )
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.code, "not_draft")
        self.assertIsNone(store.read("1:1"))
        self.assertEqual(logger.events[-1].event, "use_case_refused")


if __name__ == "__main__":
    unittest.main()
