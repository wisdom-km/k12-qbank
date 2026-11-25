"""Catalog lines become chapters, sections, and lessons. The report keeps line numbers only."""

from __future__ import annotations

import unittest
from dataclasses import replace

from backend.catalog.application.book_toc import TocLine, lesson_order_for, lessons_changed, parse_toc
from backend.catalog.application.lesson_view import issuable, lesson_tree, placement
from backend.catalog.domain.snapshot import ApprovalSnapshot


class BookTocTest(unittest.TestCase):
    def test_chapters_sections_lessons_and_ignored_lines(self) -> None:
        text = "\n".join(
            [
                "# 目录",
                "# 课课练",
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
        parsed, reason = parse_toc([{"pdf_page": 1, "text": text}], 0, 10)
        self.assertEqual(reason, "")
        assert parsed is not None
        self.assertEqual(parsed.chapters, 1)
        self.assertEqual(parsed.sections, 1)
        self.assertEqual(len(parsed.lessons), 4)
        self.assertEqual(parsed.unparsed, (TocLine(1, 11),))
        self.assertEqual([item.start_page for item in parsed.lessons], [1, 4, 6, 8])
        self.assertEqual([item.end_page for item in parsed.lessons], [3, 5, 7, 10])
        self.assertEqual(parsed.lessons[0].section_title, "synth-sec")
        self.assertEqual(parsed.lessons[0].chapter_title, "一、synth-ch")
        self.assertEqual(lesson_order_for(1, parsed.lessons), 1)
        self.assertEqual(lesson_order_for(10, parsed.lessons), 4)
        self.assertIsNone(lesson_order_for(0, parsed.lessons))

    def test_a_second_chapter_resets_the_section_and_the_offset_moves_the_start(self) -> None:
        text = "\n".join(
            [
                "## 一、synth-a",
                "synth-sec-a",
                "synth-one \u2026 1",
                "## 二、synth-b",
                "synth-two ... 3",
            ]
        )
        parsed, reason = parse_toc([{"pdf_page": 2, "text": text}], 10, 20)
        self.assertEqual(reason, "")
        assert parsed is not None
        self.assertEqual(parsed.chapters, 2)
        self.assertEqual(parsed.sections, 1)
        self.assertEqual(parsed.lessons[0].start_page, 11)
        self.assertEqual(parsed.lessons[0].end_page, 12)
        self.assertEqual(parsed.lessons[1].start_page, 13)
        self.assertEqual(parsed.lessons[1].end_page, 20)
        self.assertIsNone(parsed.lessons[1].section_title)
        self.assertEqual(parsed.lessons[1].chapter_order, 2)

    def test_a_line_before_any_chapter_is_unparsed_and_a_short_range_does_not_run_backwards(self) -> None:
        text = "\n".join(["synth-loose \u2026 1", "## 一、synth-ch", "synth-late \u2026 4", "synth-early \u2026 4"])
        parsed, reason = parse_toc([{"pdf_page": 1, "text": text}], 0, 4)
        self.assertEqual(reason, "")
        assert parsed is not None
        self.assertEqual(parsed.unparsed, (TocLine(1, 1),))
        self.assertEqual(parsed.lessons[0].start_page, 4)
        self.assertEqual(parsed.lessons[0].end_page, 4)
        self.assertEqual(parsed.lessons[1].start_page, 4)
        self.assertEqual(parsed.lessons[1].end_page, 4)

    def test_the_last_lesson_stops_at_its_own_start_when_the_book_ends_earlier(self) -> None:
        text = "## 一、synth-ch\nsynth-far \u2026 8\n"
        parsed, _reason = parse_toc([{"pdf_page": 1, "text": text}], 0, 1)
        assert parsed is not None
        self.assertEqual(parsed.lessons[0].start_page, 8)
        self.assertEqual(parsed.lessons[0].end_page, 8)

    def test_spacing_and_fullwidth_parentheses_are_the_same_lesson(self) -> None:
        first, _reason = parse_toc([{"pdf_page": 1, "text": "## 一、synth-ch\nsynth-les (1) \u2026 1\n"}], 0, 1)
        second, _reason = parse_toc(
            [{"pdf_page": 1, "text": "## 一、synth-ch\nsynth-les（1） \u2026 1\n"}],
            0,
            1,
        )
        spaced, _reason = parse_toc(
            [{"pdf_page": 1, "text": "## 一、synth-ch\nsynth- les (1) \u2026 1\n"}],
            0,
            1,
        )
        other, _reason = parse_toc([{"pdf_page": 1, "text": "## 一、synth-ch\nsynth-other \u2026 1\n"}], 0, 1)
        assert first is not None and second is not None and spaced is not None and other is not None
        self.assertFalse(lessons_changed((), first.lessons))
        self.assertFalse(lessons_changed(first.lessons, second.lessons))
        self.assertFalse(lessons_changed(first.lessons, spaced.lessons))
        self.assertTrue(lessons_changed(first.lessons, other.lessons))

    def test_a_missing_catalog_is_not_a_document_and_a_bad_offset_is_rejected(self) -> None:
        self.assertEqual(parse_toc(None, 0, 1), (None, ""))
        self.assertEqual(parse_toc([], 0, 1), (None, ""))
        _parsed, reason = parse_toc([{"pdf_page": 1, "text": "## 一、synth-ch\n"}], -1, 1)
        self.assertEqual(reason, "unknown_field")
        _parsed, reason = parse_toc([{"pdf_page": 1, "text": "## 一、synth-ch\n"}], True, 1)
        self.assertEqual(reason, "unknown_field")
        _parsed, reason = parse_toc({"pdf_page": 1}, 0, 1)
        self.assertEqual(reason, "unknown_field")


class LessonTreeTest(unittest.TestCase):
    def test_only_an_approved_question_inside_the_range_counts(self) -> None:
        parsed, _reason = parse_toc(
            [{"pdf_page": 1, "text": "## 一、synth-ch\nsynth-sec\nsynth-les \u2026 1\n"}],
            0,
            4,
        )
        assert parsed is not None
        ready = _snap(True, 1)
        draft = _snap(False, 1, "qv-synth-r4f-draft")
        outside = _snap(True, 9, "qv-synth-r4f-out")
        broken = replace(ready, question_version_id="qv-synth-r4f-bad", stem_parts=(("math", r"\sqrt{2}"),))
        tree = lesson_tree("synth-r4f", parsed.lessons, (ready, draft, outside, broken))
        lesson = tree["chapters"][0]["sections"][0]["lessons"][0]  # type: ignore[index]
        self.assertEqual(lesson["issuable_count"], 1)  # type: ignore[index]
        self.assertEqual(lesson["title"], "synth-les")  # type: ignore[index]
        self.assertEqual(placement(outside, parsed.lessons)["lesson_order"], 0)
        self.assertEqual(placement(ready, parsed.lessons)["lesson_title"], "synth-les")
        self.assertFalse(issuable(draft))
        self.assertFalse(issuable(broken))
        loose = placement(replace(ready, book_id=None), parsed.lessons)
        self.assertEqual(loose["book_id"], "")
        self.assertEqual(loose["lesson_order"], 0)


def _snap(approved: bool, page: int, question_id: str = "qv-synth-r4f") -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=question_id,
        answer_version_id="av-" + question_id,
        asset_ids=(),
        layout_template_id="",
        question_approved=approved,
        answer_approved=approved,
        retired=False,
        subject_id="math",
        stem="synth-stem",
        answer_text="synth-a",
        stem_parts=(("text", "synth-stem"),),
        book_id="synth-r4f",
        pdf_page=page,
    )
