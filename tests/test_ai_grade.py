"""Local grading. Unreadable is not marked wrong."""

from __future__ import annotations

import unittest

from backend.ai.domain.grade import grade_local
from backend.ai.domain.payload import PAGE_H, parse_transcribe, relative_box


class LocalGradeTest(unittest.TestCase):
    def test_choice_ignores_case(self) -> None:
        graded = grade_local("single_choice", "A", "a", False, 0)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "correct")

    def test_choice_folds_fullwidth(self) -> None:
        graded = grade_local("single_choice", "A", "Ａ", False, 0)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "correct")

    def test_choice_ignores_spaces(self) -> None:
        graded = grade_local("multiple_choice", "AB", "A B", False, 0)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "correct")

    def test_choice_sorts_multiple_letters(self) -> None:
        graded = grade_local("multiple_choice", "AC", "C,A", False, 0)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "correct")

    def test_fill_negative(self) -> None:
        graded = grade_local("fill_blank", "-3", "－3", False, 1)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "correct")
        self.assertEqual(graded.reason, "与标准答案一致")

    def test_fill_decimal(self) -> None:
        graded = grade_local("fill_blank", "3.14", "３．１４", False, 1)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "correct")

    def test_unreadable_is_unsure_and_not_wrong(self) -> None:
        graded = grade_local("single_choice", "A", "", True, 0)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "unsure")
        self.assertEqual(graded.reason, "看不清")

    def test_fill_partial_when_one_blank_matches(self) -> None:
        graded = grade_local("fill_blank", "1\n2", "1\n9", False, 2)
        self.assertIsNotNone(graded)
        assert graded is not None
        self.assertEqual(graded.verdict, "partial")
        self.assertEqual(graded.reason, "部分空与标准答案一致")

    def test_mixed_fill_goes_to_the_model(self) -> None:
        self.assertIsNone(grade_local("fill_blank", "3", "约 3", False, 1))
        self.assertIsNone(grade_local("solution", "2", "2", False, 0))

    def test_relative_box_uses_the_top_of_the_page(self) -> None:
        box = relative_box(0, 0, PAGE_H, 10)
        self.assertGreater(box.y, 0.9)

    def test_transcribe_parse_rejects_a_missing_item(self) -> None:
        from backend.ai.domain.model import ModelFault

        with self.assertRaises(ModelFault) as caught:
            parse_transcribe(
                {"items": [{"order_no": 1, "transcription": "2", "unreadable": False, "confidence": 0.5}]},
                (1, 2),
            )
        self.assertEqual(caught.exception.code, "model_output_invalid")
