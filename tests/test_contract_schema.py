"""Shipped JSON Schemas accept the current draft files and reject a wrong shape."""

from __future__ import annotations

import unittest

from backend.catalog.domain.answer import parse_answer_draft
from backend.catalog.domain.parse import parse_question_draft
from backend.catalog.domain.schema_check import (
    load_contract_schema,
    schema_problems,
    unknown_schema_keywords,
)
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


class ContractSchemaTest(unittest.TestCase):
    def test_keywords_in_the_files_are_implemented(self) -> None:
        for name in ("k12-question-draft.v1.schema.json", "k12-answer-draft.v1.schema.json"):
            self.assertEqual(unknown_schema_keywords(load_contract_schema(name)), [])

    def test_current_question_and_answer_files_match(self) -> None:
        question = draft_file(
            questions=[
                one_question(
                    type="composite",
                    structure="composite",
                    options=[],
                    subquestions=[
                        {
                            "number": "1",
                            "type": "single_choice",
                            "structure": "choice",
                            "stem": [{"type": "text", "value": "选一个"}],
                            "options": [
                                {"key": "A", "content": [{"type": "text", "value": "2"}]},
                                {"key": "B", "content": [{"type": "math", "latex": "3"}]},
                            ],
                        },
                        {"number": "2", "type": "fill_blank", "structure": "blank", "stem": [{"type": "text", "value": "填"}]},
                    ],
                    geometry={"kind": "editable-geometry", "version": 1, "document": {"points": []}},
                )
            ]
        )
        self.assertEqual(schema_problems(load_contract_schema("k12-question-draft.v1.schema.json"), question), [])
        self.assertIsInstance(parse_question_draft(question), Ok)
        answer = answer_file(
            parts=[{"sub_key": "1", "role": "step", "order": 1, "content": [{"type": "text", "value": "移项"}]}]
        )
        self.assertEqual(schema_problems(load_contract_schema("k12-answer-draft.v1.schema.json"), answer), [])
        self.assertIsInstance(parse_answer_draft(answer), Ok)

    def test_wrong_shape_names_the_field_and_writes_nothing(self) -> None:
        page = parse_question_draft([{"index": 0}])
        self.assertIsInstance(page, Err)
        assert isinstance(page, Err)
        self.assertEqual(page.code, "not_draft")
        self.assertIn("$", page.message)
        extra = draft_file()
        extra["note"] = "no"
        refused = parse_question_draft(extra)
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("note", refused.message)
        true_version = parse_answer_draft(answer_file(contract_version=True))
        self.assertIsInstance(true_version, Err)
        assert isinstance(true_version, Err)
        self.assertIn("contract_version", true_version.message)
        model = parse_answer_draft(
            answer_file(origin="model", key="1:1:model:1", applicable=True, source={"model_task_id": "task-1"})
        )
        self.assertIsInstance(model, Err)
        assert isinstance(model, Err)
        self.assertIn("applicable", model.message)

    def test_k12_question_draft_unknown_schema_version_is_not_draft(self) -> None:
        unknown = parse_question_draft(draft_file(schema_version=2))
        self.assertIsInstance(unknown, Err)
        assert isinstance(unknown, Err)
        self.assertEqual(unknown.code, "not_draft")
        self.assertIn("收到的版本是 2", unknown.message)
        missing = draft_file()
        del missing["schema_version"]
        refused = parse_question_draft(missing)
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("没有 schema_version", refused.message)

    def test_k12_answer_draft_dispatches_on_schema_id_and_version(self) -> None:
        schema = load_contract_schema("k12-answer-draft.v1.schema.json")
        self.assertEqual(schema["version"], 1)
        self.assertIn("k12-answer-draft.v1.schema.json", schema["$id"])
        unknown = parse_answer_draft(answer_file(schema_version=True))
        self.assertIsInstance(unknown, Err)
        assert isinstance(unknown, Err)
        self.assertEqual(unknown.code, "not_draft")
        self.assertIn("收到的版本是 True", unknown.message)


if __name__ == "__main__":
    unittest.main()
