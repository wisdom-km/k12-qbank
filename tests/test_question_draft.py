"""The review tool's draft file can be read. It cannot be issued."""

from __future__ import annotations

import unittest

from backend.catalog.api import parse_question_draft, publication_blocked
from backend.kernel.result import Err, Ok


def one_question(**changes: object) -> dict:
    question = {
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
    question.update(changes)
    return question


def draft_file(**changes: object) -> dict:
    payload = {
        "contract": "k12-question-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "preface": "",
        "source": {"pdf_page": 1},
        "questions": [one_question()],
    }
    payload.update(changes)
    return payload


class QuestionDraftTest(unittest.TestCase):
    def test_crop_is_kept_and_geometry_stays_empty(self) -> None:
        parsed = parse_question_draft(draft_file())
        self.assertIsInstance(parsed, Ok)
        question = parsed.value.questions[0]
        self.assertEqual(question.assets[0].bbox, (0.0, 0.0, 10.0, 20.0))
        self.assertIsNone(question.geometry)
        self.assertIsInstance(question.stem[1].latex, str)

    def test_reserved_geometry_is_stored_and_not_issued(self) -> None:
        question = one_question(geometry={"kind": "editable-geometry", "version": 1, "document": {"points": []}})
        parsed = parse_question_draft(draft_file(questions=[question]))
        self.assertIsInstance(parsed, Ok)
        slot = parsed.value.questions[0].geometry
        self.assertIsNotNone(slot)
        assert slot is not None
        self.assertEqual(slot.document_json, '{"points":[]}')
        blocked = publication_blocked(parsed.value.questions[0])
        self.assertIsInstance(blocked, Err)
        self.assertEqual(blocked.code, "draft")

    def test_page_blocks_and_bad_geometry_are_refused(self) -> None:
        page = parse_question_draft([[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None}]])
        self.assertIsInstance(page, Err)
        self.assertEqual(page.code, "not_draft")
        bad = one_question(geometry={"kind": "svg", "version": 1, "document": {}})
        refused = parse_question_draft(draft_file(questions=[bad]))
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.code, "not_draft")

    def test_composite_reuses_part_shapes_and_unknown_codes_are_refused(self) -> None:
        choice = {
            "number": "1",
            "type": "single_choice",
            "structure": "choice",
            "stem": [{"type": "text", "value": "选一个"}],
            "options": [
                {"key": "A", "content": [{"type": "text", "value": "2"}]},
                {"key": "B", "content": [{"type": "text", "value": "3"}]},
            ],
        }
        blank = {
            "number": "2",
            "type": "fill_blank",
            "structure": "blank",
            "stem": [{"type": "text", "value": "填一个"}],
        }
        question = one_question(type="composite", structure="composite", options=[], subquestions=[choice, blank])
        parsed = parse_question_draft(draft_file(questions=[question]))
        self.assertIsInstance(parsed, Ok)
        parts = parsed.value.questions[0].subquestions
        self.assertEqual(parts[0].structure, "choice")
        self.assertEqual(len(parts[0].options), 2)
        self.assertEqual(parts[1].structure, "blank")
        unknown = parse_question_draft(draft_file(questions=[one_question(type="judgment", structure="choice")]))
        self.assertIsInstance(unknown, Err)
        self.assertEqual(unknown.code, "not_draft")


if __name__ == "__main__":
    unittest.main()
