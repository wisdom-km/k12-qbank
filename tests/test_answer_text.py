"""Answer text joins sub-questions. A content-only answer stays the old plain string."""

from __future__ import annotations

import unittest

from backend.catalog.application.answer_text import answer_plain
from backend.catalog.domain.answer import AnswerDraft, AnswerPart, TextPart


class AnswerTextTest(unittest.TestCase):
    def test_parts_follow_their_sub_question_and_content_only_is_unchanged(self) -> None:
        joined = answer_plain(
            _answer(
                (),
                (
                    AnswerPart("1", "result", 2, (TextPart("synth-a"),)),
                    AnswerPart("1", "step", 3, (TextPart("synth-step"),)),
                    AnswerPart("2", "result", 1, (TextPart("synth-b"),)),
                ),
            )
        )
        self.assertEqual(joined, "(2) synth-b；(1) synth-a synth-step")
        self.assertEqual(answer_plain(_answer((TextPart("synth-only"),), ())), "synth-only")
        labeled = answer_plain(
            _answer(
                (TextPart("lead"),),
                (AnswerPart("(1)", "result", 1, (TextPart("synth-a"),)),),
            )
        )
        self.assertEqual(labeled, "lead；(1) synth-a")
        shared = answer_plain(
            _answer(
                (),
                (
                    AnswerPart("", "step", 1, (TextPart("synth-shared"),)),
                    AnswerPart("", "step", 2, (TextPart("synth-next"),)),
                ),
            )
        )
        self.assertEqual(shared, "synth-shared synth-next")
        self.assertNotIn("()", shared)


def _answer(content: tuple[TextPart, ...], parts: tuple[AnswerPart, ...]) -> AnswerDraft:
    return AnswerDraft(
        question_key="1:1",
        key="1:1:ocr:1",
        origin="ocr",
        status="confirmed",
        applicable=True,
        pdf_page=1,
        model_task_id=None,
        content=content,
        parts=parts,
        assets=(),
        ok=True,
        reason="",
    )
