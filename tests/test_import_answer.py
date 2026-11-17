"""One OCR answer file is stored as itself. It is not published."""

from __future__ import annotations

import unittest

from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.application.import_answer import import_answer_draft
from backend.catalog.domain.answer import answer_not_publication, parse_answer_draft
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


def answer_file(**overrides: object) -> dict:
    payload = {
        "contract": "k12-answer-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "question_key": "1:1",
        "key": "1:1:ocr:1",
        "origin": "ocr",
        "status": "confirmed",
        "applicable": True,
        "source": {"pdf_page": 1},
        "content": [{"type": "text", "value": "A"}],
        "parts": [],
        "assets": [],
    }
    payload.update(overrides)
    return payload


class ImportAnswerTest(unittest.TestCase):
    def test_review_file_is_stored_without_a_second_shape(self) -> None:
        store = MemoryAnswers()
        logger = ListLog()
        imported = import_answer_draft(answer_file(), store, logger, "req-answer")
        self.assertIsInstance(imported, Ok)
        stored = store.read("1:1:ocr:1")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.content[0].value, "A")
        self.assertEqual(stored.pdf_page, 1)
        self.assertIsNone(stored.model_task_id)
        self.assertTrue(stored.applicable)
        self.assertFalse(hasattr(stored, "answer_version_id"))
        self.assertEqual(answer_not_publication(stored).code, "draft")
        self.assertEqual(logger.events[-1].event, "answer_imported")
        self.assertEqual(logger.events[-1].outcome, "1")
        self.assertNotIn("A", logger.events[-1].outcome)

    def test_page_blocks_and_a_true_version_are_refused(self) -> None:
        store = MemoryAnswers()
        logger = ListLog()
        refused = import_answer_draft(
            [[{"index": 0, "label": "text", "content": "A", "bbox_2d": None}]],
            store,
            logger,
            "req-page",
        )
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.code, "not_draft")
        self.assertIsNone(store.read("1:1:ocr:1"))
        self.assertEqual(logger.events[-1].event, "use_case_refused")
        true_version = answer_file(contract_version=True)
        self.assertIsInstance(parse_answer_draft(true_version), Err)

    def test_model_and_unconfirmed_answers_cannot_be_applicable(self) -> None:
        model = answer_file(
            origin="model",
            key="1:1:model:1",
            applicable=True,
            source={"model_task_id": "task-1"},
        )
        self.assertEqual(parse_answer_draft(model).code, "not_draft")
        candidate = answer_file(status="candidate", applicable=True)
        self.assertEqual(parse_answer_draft(candidate).code, "not_draft")
        quiet = answer_file(
            origin="model",
            key="1:1:model:1",
            status="candidate",
            applicable=False,
            source={"model_task_id": "task-1"},
        )
        parsed = parse_answer_draft(quiet)
        self.assertIsInstance(parsed, Ok)
        assert isinstance(parsed, Ok)
        self.assertEqual(parsed.value.model_task_id, "task-1")
        self.assertIsNone(parsed.value.pdf_page)

    def test_a_second_applicable_answer_writes_nothing(self) -> None:
        store = MemoryAnswers()
        logger = ListLog()
        first = import_answer_draft(answer_file(), store, logger, "req-one")
        self.assertIsInstance(first, Ok)
        other = answer_file(key="1:1:ocr:2", content=[{"type": "text", "value": "C"}])
        refused = import_answer_draft(other, store, logger, "req-two")
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.code, "answer_conflict")
        self.assertIsNone(store.read("1:1:ocr:2"))
        kept = store.read("1:1:ocr:1")
        assert kept is not None
        self.assertEqual(kept.content[0].value, "A")
        self.assertEqual(logger.events[-1].event, "use_case_refused")
        self.assertEqual(logger.events[-1].outcome, "answer_conflict")

    def test_the_same_key_can_be_replaced(self) -> None:
        store = MemoryAnswers()
        logger = ListLog()
        import_answer_draft(answer_file(), store, logger, "req-old")
        again = import_answer_draft(
            answer_file(content=[{"type": "text", "value": "B"}]),
            store,
            logger,
            "req-new",
        )
        self.assertIsInstance(again, Ok)
        stored = store.read("1:1:ocr:1")
        assert stored is not None
        self.assertEqual(stored.content[0].value, "B")

    def test_a_store_failure_is_logged_without_the_answer(self) -> None:
        class Boom:
            def put(self, answer: object) -> str | None:
                raise RuntimeError("disk")

        logger = ListLog()
        failed = import_answer_draft(answer_file(), Boom(), logger, "req-disk")
        self.assertIsInstance(failed, Err)
        self.assertEqual(failed.code, "store_failed")
        self.assertEqual(logger.events[-1].event, "use_case_failed")
        self.assertEqual(logger.events[-1].outcome, "store_failed")


if __name__ == "__main__":
    unittest.main()
