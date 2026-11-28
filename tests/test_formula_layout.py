"""Formula layout, issue refusal, and a rendered page that does not print source."""

from __future__ import annotations

import re
import unittest
from dataclasses import replace

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.publish_version import revise_text
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.adapters.pdf_font import load_system_face
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.application.compose_multi import compose_multi_item_paper
from backend.practice.application.issue_flow import place_flow
from backend.practice.application.render_paper import page_faces
from backend.practice.domain.flow_layout import FlowQuestion, FormulaStop, ItemTooLong, dump_layout, flow_place
from backend.practice.domain.formula import (
    FormulaFault,
    layout_math,
    layout_question,
    place_lines,
    plain_has_command,
    unsupported_commands,
)
from backend.practice.domain.item import ItemBox, PracticeItem
from backend.practice.domain.layout_params import load_layout
from backend.practice.domain.page_face import PaperPage
from backend.practice.domain.page_layout import pack_items
from backend.practice.domain.paper import Paper, freeze_paper

_SIZE = 12.0


class _Log:
    def log(self, event: LogEvent) -> None:
        self.events.append(event)

    def __init__(self) -> None:
        self.events: list[LogEvent] = []


class FormulaLayoutTest(unittest.TestCase):
    def test_fraction_stacks_the_numerator_above_the_bar(self) -> None:
        box = layout_math(r"\frac{1}{2}", _SIZE)
        bar = _bars(box.rules)
        self.assertEqual(len(bar), 1)
        one = _glyph(box, "1")
        two = _glyph(box, "2")
        self.assertGreater(one.y, bar[0].y1)
        self.assertLess(two.y, bar[0].y1)
        self.assertGreater(box.height, _SIZE)
        self.assertGreater(box.width, 0)
        self.assertEqual(box.baseline, box.descent)
        again = layout_math(r"\frac{1}{2}", _SIZE)
        self.assertEqual(again, box)

    def test_dfrac_and_tfrac_use_the_same_stack(self) -> None:
        base = layout_math(r"\frac{1}{2}", _SIZE)
        self.assertEqual(layout_math(r"\dfrac{1}{2}", _SIZE), base)
        self.assertEqual(layout_math(r"\tfrac{1}{2}", _SIZE), base)

    def test_superscript_rises_and_subscript_drops_at_a_smaller_size(self) -> None:
        sup = layout_math("a^{2}", _SIZE)
        base = _glyph(sup, "a")
        two = _glyph(sup, "2")
        self.assertGreater(two.y, base.y)
        self.assertAlmostEqual(two.size, _SIZE * 0.7)
        sub = layout_math("a_{1}", _SIZE)
        one = _glyph(sub, "1")
        self.assertLess(one.y, 0)
        self.assertAlmostEqual(one.size, _SIZE * 0.7)

    def test_nested_fraction_mixed_number_and_absolute_value(self) -> None:
        nested = layout_math(r"\frac{1}{\frac{2}{3}}", _SIZE)
        bars = _bars(nested.rules)
        self.assertEqual(len(bars), 2)
        self.assertGreater(max(bar.y1 for bar in bars), min(bar.y1 for bar in bars))
        mixed = layout_math(r"2\frac{1}{3}", _SIZE)
        self.assertGreater(mixed.width, layout_math(r"\frac{1}{3}", _SIZE).width)
        self.assertEqual(_glyph(mixed, "2").y, 0)
        wrapped = layout_math(r"\left| \frac{1}{2} \right|", _SIZE)
        upright = [rule for rule in wrapped.rules if rule.x1 == rule.x2]
        self.assertEqual(len(upright), 2)
        self.assertGreater(upright[0].y2 - upright[0].y1, _SIZE)
        bare = layout_math("|x|", _SIZE)
        self.assertEqual(len([rule for rule in bare.rules if rule.x1 == rule.x2]), 2)
        self.assertEqual([glyph.text for glyph in bare.glyphs], ["x"])

    def test_parentheses_stretch_and_scripts_bind_to_the_previous_atom(self) -> None:
        stretched = layout_math(r"\left( \frac{1}{2} \right)", _SIZE)
        paren = _glyph(stretched, "(")
        self.assertGreater(paren.scale_y, 1)
        self.assertEqual(paren.font, "latin")
        squared = layout_math("(-3)^{2}", _SIZE)
        close = _glyph(squared, ")")
        two = _glyph(squared, "2")
        self.assertGreater(two.y, close.y)
        self.assertGreater(two.x, close.x)
        power = layout_math("-2^{3}", _SIZE)
        minus = _glyph(power, "-")
        base = _glyph(power, "2")
        three = _glyph(power, "3")
        self.assertEqual(minus.y, 0)
        self.assertGreater(three.y, base.y)
        term = layout_math("3a^{2}b", _SIZE)
        letter = _glyph(term, "a")
        exponent = [glyph for glyph in term.glyphs if glyph.text == "2"][0]
        trail = _glyph(term, "b")
        self.assertGreater(exponent.y, letter.y)
        self.assertGreater(trail.x, letter.x)
        self.assertEqual(trail.y, 0)

    def test_operators_angle_text_and_spacing(self) -> None:
        ops = layout_math(r"\times\div\pm\cdot\neq\approx\leq\geq\le\ge", _SIZE)
        self.assertEqual([glyph.text for glyph in ops.glyphs], list("×÷±·≠≈≤≥≤≥"))
        self.assertTrue(all(glyph.font == "cjk" for glyph in ops.glyphs))
        angle = layout_math(r"\angle AOB=90^{\circ}", _SIZE)
        self.assertEqual(_glyph(angle, "∠").font, "cjk")
        degree = _glyph(angle, "°")
        self.assertGreater(degree.y, 0)
        self.assertAlmostEqual(degree.size, _SIZE * 0.7)
        self.assertIn("π", [glyph.text for glyph in layout_math(r"\pi", _SIZE).glyphs])
        self.assertIn("′", [glyph.text for glyph in layout_math(r"\prime", _SIZE).glyphs])
        self.assertEqual(_glyph(layout_math(r"\%", _SIZE), "%").text, "%")
        word = layout_math(r"\text{甲}", _SIZE)
        self.assertEqual(_glyph(word, "甲").font, "cjk")
        roman = layout_math(r"\mathrm{甲}", _SIZE)
        self.assertEqual(_glyph(roman, "甲").font, "cjk")
        tight = layout_math("ab", _SIZE)
        spaced = layout_math(r"a\,b", _SIZE)
        self.assertGreater(spaced.width, tight.width)
        self.assertGreater(layout_math(r"a\quad b", _SIZE).width, layout_math("a~b", _SIZE).width)

    def test_an_unknown_command_names_itself_and_returns_no_glyphs(self) -> None:
        self.assertEqual(unsupported_commands(r"\sqrt{2}+\frac{1}{2}"), (r"\sqrt",))
        with self.assertRaises(FormulaFault) as caught:
            layout_math(r"\sqrt{2}", _SIZE)
        self.assertEqual(caught.exception.code, "formula_unsupported")
        self.assertEqual(caught.exception.command, r"\sqrt")
        self.assertFalse(plain_has_command("(-3)+5"))
        self.assertTrue(plain_has_command(r"计算：\frac{1}{2}"))

    def test_a_formula_wider_than_the_line_is_refused_and_a_narrow_first_line_wraps_whole(self) -> None:
        with self.assertRaises(FormulaFault) as caught:
            layout_question("", (("math", "x" * 40),), (), size=_SIZE, first_width=20, width=20)
        self.assertEqual(caught.exception.code, "formula_too_wide")
        rows = layout_question("", (("math", "abc"),), (), size=11, first_width=10, width=100)
        self.assertEqual(rows[0].glyphs, ())
        self.assertEqual([glyph.text for glyph in rows[1].glyphs], ["a", "b", "c"])

    def test_a_fraction_makes_the_next_question_start_lower_and_the_place_is_stable(self) -> None:
        params = load_layout()
        plain = (
            FlowQuestion(1, "qv-synth-a", "synth-a", (), "medium", 1),
            FlowQuestion(2, "qv-synth-b", "synth-b", (), "medium", 1),
        )
        fraction = (
            FlowQuestion(
                1,
                "qv-synth-a",
                r"synth:\frac{1}{2}",
                (),
                "medium",
                1,
                stem_parts=(("math", r"\frac{1}{2}"),),
                option_parts=(),
            ),
            plain[1],
        )
        first = flow_place(plain, params)
        tall = flow_place(fraction, params)
        self.assertNotIsInstance(first, ItemTooLong)
        self.assertNotIsInstance(tall, ItemTooLong)
        assert not isinstance(first, ItemTooLong)
        assert not isinstance(tall, FormulaStop)
        assert not isinstance(tall, ItemTooLong)
        self.assertLess(tall[1].boxes[0].y, first[1].boxes[0].y)
        self.assertGreater(tall[0].draw[0][4], 0)  # type: ignore[index]
        self.assertEqual(flow_place(fraction, params), tall)
        self.assertEqual(tall[0].lines, ())

    def test_issue_refuses_unsupported_unstructured_and_too_wide_without_writing(self) -> None:
        params = load_layout()
        bad = FlowQuestion(
            1,
            "qv-synth-sqrt",
            r"\sqrt{2}",
            (),
            "medium",
            1,
            stem_parts=(("math", r"\sqrt{2}"),),
            option_parts=(),
        )
        stopped = flow_place((bad,), params)
        self.assertIsInstance(stopped, FormulaStop)
        assert isinstance(stopped, FormulaStop)
        self.assertEqual(stopped.code, "formula_unsupported")
        self.assertEqual(stopped.command, r"\sqrt")
        item = _item(r"\sqrt{2}", stem_parts=(("math", r"\sqrt{2}"),), option_parts=())
        snapshot = _snapshot(item.question_version_id, item.stem_text, item.stem_parts, item.option_parts)
        refused = place_flow((item,), (snapshot,))
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertEqual(refused.code, "formula_unsupported")
        self.assertIn("qv-synth-sqrt", refused.message)
        self.assertIn(r"\sqrt", refused.message)
        self.assertNotIn("{2}", refused.message)
        old = _item(r"计算：\frac{1}{2}")
        unstructured = place_flow((old,), (_snapshot(old.question_version_id, old.stem_text, None, None),))
        self.assertIsInstance(unstructured, Err)
        assert isinstance(unstructured, Err)
        self.assertEqual(unstructured.code, "formula_unstructured")
        self.assertIn(old.question_version_id, unstructured.message)
        wide = _item("x" * 120, stem_parts=(("math", "x" * 120),), option_parts=())
        too_wide = place_flow((wide,), (_snapshot(wide.question_version_id, wide.stem_text, wide.stem_parts, ()),))
        self.assertIsInstance(too_wide, Err)
        assert isinstance(too_wide, Err)
        self.assertEqual(too_wide.code, "formula_too_wide")
        writer = _Writer()
        composed = compose_multi_item_paper(
            "paper-synth-formula",
            (_item(r"\frac{1}{2}", "qv-synth-u1", order=1), _item("synth-b", "qv-synth-u2", order=2)),
            teacher_id="teacher-synth",
            student_id="student-synth",
            review_version_id="rev-synth",
            approvals=_Approvals(),
            publications=_Publications(),
            writer=writer,
        )
        self.assertIsInstance(composed, Err)
        assert isinstance(composed, Err)
        self.assertEqual(composed.code, "formula_unstructured")
        self.assertFalse(writer.called)

    def test_an_old_flow_paper_keeps_its_stored_lines(self) -> None:
        params = load_layout()
        question = FlowQuestion(1, "qv-synth-old", "synth-old (-3)+5", (), "medium", 1)
        placed = flow_place((question,), params)
        again = flow_place((question,), params)
        self.assertEqual(placed, again)
        assert not isinstance(placed, ItemTooLong)
        assert not isinstance(placed, FormulaStop)
        item = PracticeItem(
            paper_id="paper-synth-old",
            order_no=1,
            question_version_id="qv-synth-old",
            answer_version_id="av-synth-old",
            stem_text="synth-old (-3)+5",
            page_no=placed[0].page_no,
            placed_lines=tuple((line.text, line.x, line.y) for line in placed[0].lines),
            formula_draw=None,
        )
        frozen = freeze_paper(
            paper_id=item.paper_id,
            teacher_id="teacher-synth",
            student_id="student-synth",
            subject_id="math",
            question_version_id=item.question_version_id,
            answer_version_id=item.answer_version_id,
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-synth",
            item_order=("sq-1",),
            slots_per_page=1,
            layout_kind="flow",
            layout_params="{}",
            printed_external_id="synth-0001",
        )
        assert not isinstance(frozen, Err)
        face = page_faces(frozen, (item,))[0]
        body = [row for row in face.flow_lines if row[0] == item.placed_lines[0][0]]
        self.assertEqual((body[0][0], body[0][1], body[0][2]), item.placed_lines[0])

    def test_a_choice_slot_and_the_pdf_stream_have_no_command(self) -> None:
        stem_parts = (("math", r"2\frac{1}{3}+\left|(-3)^{2}\right|-2^{3}"),)
        option_parts = (
            ("A", (("math", r"\frac{1}{2}"),)),
            ("B", (("math", r"\frac{3}{4}"),)),
        )
        item = _item("synth", "qv-synth-slot", stem_parts=stem_parts, option_parts=option_parts)
        packed = pack_items((item,), 4)
        self.assertIsNotNone(packed[0].formula_draw)
        self.assertEqual(packed[0].placed_lines, ())
        ops, _height = place_lines(
            layout_question("1. ", (("math", r"\frac{1}{2}"),), (), size=12, first_width=480, width=480),
            48,
            700,
            16,
        )
        runs = tuple(op[1:] for op in ops if op[0] == "g")
        rules = tuple(op[1:] for op in ops if op[0] == "r")
        page = PaperPage(
            question_version_id="qv-synth",
            answer_version_id="av-synth",
            formula="",
            student_id="student-synth",
            page_number=1,
            item_order=(),
            asset_ids=(),
            layout_template_id="",
            paper_id="paper-synth",
            page_count=1,
            extra_runs=runs,
            draw_rules=rules,  # type: ignore[arg-type]
        )
        drawn = StdPdf().render(page)
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        text = drawn.decode("latin-1")
        self.assertIsNone(re.search(r"\\[A-Za-z]", text))
        self.assertNotIn("frac", text)
        self.assertIn("(1)", text)
        self.assertIn("(2)", text)
        self.assertIn(" l S", text)

    def test_breaks_and_tabs_split_rows_and_leave_no_control_glyph(self) -> None:
        parts = (("text", "line-a\nline-b\r\nline-c\rline-d\tline-e"),)
        rows = layout_question("", parts, (), size=10, first_width=400, width=400)
        self.assertEqual(_row_text(rows), ["line-a", "line-b", "line-c", "line-d line-e"])
        _assert_no_controls(self, rows)

    def test_repeated_breaks_add_no_blank_row_and_the_next_row_uses_the_full_width(self) -> None:
        leading = layout_question("", (("text", "\n\nab\n\n"),), (), size=10, first_width=15, width=80)
        self.assertEqual(_row_text(leading), ["ab"])
        _assert_no_controls(self, leading)
        wrapped = layout_question("", (("text", "ab\ncdefghij"),), (), size=10, first_width=15, width=80)
        self.assertEqual(_row_text(wrapped), ["ab", "cdefghij"])
        _assert_no_controls(self, wrapped)
        opened = layout_question("", (("text", "\ncdefghij"),), (), size=10, first_width=15, width=80)
        self.assertEqual(_row_text(opened), ["cdefghij"])

    def test_breaks_inside_a_formula_are_skipped_and_draw_no_control_glyph(self) -> None:
        plain = layout_math(r"\frac{1}{2}+\frac{1}{3}", _SIZE)
        broken = layout_math("\\frac{1}{2}\n+\t\\frac{1}{3}", _SIZE)
        windows = layout_math("\\frac{1}{2}\r\n+\t\\frac{1}{3}", _SIZE)
        self.assertEqual(broken, plain)
        self.assertEqual(windows, plain)
        self.assertTrue(all(ord(char) >= 32 for glyph in broken.glyphs for char in glyph.text))

    def test_a_multiline_stem_renders_a_pdf(self) -> None:
        params = load_layout()
        parts = (
            ("text", "synth-a\r\nsynth-b\tmore"),
            ("math", r"\frac{1}{2}"),
            ("text", "\nend"),
        )
        question = FlowQuestion(
            1,
            "qv-synth-ml",
            "synth-a\r\nsynth-b\tmore",
            (),
            "medium",
            1,
            stem_parts=parts,
            option_parts=(),
        )
        placed = flow_place((question,), params)
        self.assertNotIsInstance(placed, ItemTooLong)
        self.assertNotIsInstance(placed, FormulaStop)
        assert not isinstance(placed, ItemTooLong)
        assert not isinstance(placed, FormulaStop)
        drawn = placed[0]
        assert drawn.draw is not None
        self.assertTrue(all(ord(char) >= 32 for op in drawn.draw if op[0] == "g" for char in str(op[1])))
        frozen = freeze_paper(
            paper_id="paper-synth-ml",
            teacher_id="teacher-synth",
            student_id="student-synth",
            subject_id="math",
            question_version_id="qv-synth-ml",
            answer_version_id="av-synth-ml",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-synth",
            item_order=("sq-1",),
            slots_per_page=1,
            layout_kind="flow",
            layout_params=dump_layout(params),
            printed_external_id="synth-0001",
        )
        assert not isinstance(frozen, Err)
        item = PracticeItem(
            paper_id=frozen.paper_id,
            order_no=1,
            question_version_id="qv-synth-ml",
            answer_version_id="av-synth-ml",
            stem_text="synth-a synth-b more",
            answer_text="synth-hidden",
            page_no=drawn.page_no,
            placed_lines=(),
            boxes=tuple(
                ItemBox(box.box_no, box.page_no, box.x, box.y, box.w, box.h, box.kind) for box in drawn.boxes
            ),
            stem_parts=parts,
            option_parts=(),
            formula_draw=drawn.draw,
        )
        faces = page_faces(frozen, (item,))
        pdf = StdPdf().render_document(faces)
        if isinstance(pdf, Err) and pdf.code == "pdf_font_missing":
            latin = replace(
                faces[0],
                flow_lines=tuple(row for row in faces[0].flow_lines if not _row_needs_face(row)),
            )
            pdf = StdPdf().render_document((latin,))
        self.assertIsInstance(pdf, bytes)
        assert isinstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertNotIsInstance(pdf, Err)

    def test_a_chinese_multiline_stem_renders_when_a_face_is_installed(self) -> None:
        if load_system_face() is None:
            self.skipTest("no CJK face is installed")
        params = load_layout()
        parts = (("text", "synth\n\u7532\tb"), ("math", r"\frac{1}{2}"))
        question = FlowQuestion(
            1,
            "qv-synth-cjk",
            "synth",
            (),
            "medium",
            1,
            stem_parts=parts,
            option_parts=(),
        )
        placed = flow_place((question,), params)
        self.assertNotIsInstance(placed, FormulaStop)
        assert not isinstance(placed, ItemTooLong)
        assert not isinstance(placed, FormulaStop)
        drawn = placed[0]
        assert drawn.draw is not None
        frozen = freeze_paper(
            paper_id="paper-synth-cjk",
            teacher_id="teacher-synth",
            student_id="student-synth",
            subject_id="math",
            question_version_id="qv-synth-cjk",
            answer_version_id="av-synth-cjk",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-synth",
            item_order=("sq-1",),
            slots_per_page=1,
            layout_kind="flow",
            layout_params=dump_layout(params),
            printed_external_id="synth-0001",
        )
        assert not isinstance(frozen, Err)
        item = PracticeItem(
            paper_id=frozen.paper_id,
            order_no=1,
            question_version_id="qv-synth-cjk",
            answer_version_id="av-synth-cjk",
            stem_text="synth",
            page_no=drawn.page_no,
            formula_draw=drawn.draw,
            stem_parts=parts,
            option_parts=(),
        )
        pdf = StdPdf().render_document(page_faces(frozen, (item,)))
        self.assertIsInstance(pdf, bytes)
        assert isinstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_revise_clears_parts_and_an_unchanged_stem_keeps_them(self) -> None:
        approvals = MemoryApprovals()
        current = _snapshot("qv-synth-rev", r"\frac{1}{2}", (("math", r"\frac{1}{2}"),), ())
        approvals.put(current)
        same = revise_text("qv-synth-rev", current.stem, current.answer_text, approvals, _Log(), "req-synth")
        self.assertIsInstance(same, Ok)
        assert isinstance(same, Ok)
        self.assertEqual(same.value.stem_parts, current.stem_parts)
        revised = revise_text("qv-synth-rev", "plain", current.answer_text, approvals, _Log(), "req-synth")
        self.assertIsInstance(revised, Ok)
        assert isinstance(revised, Ok)
        self.assertIsNone(revised.value.stem_parts)
        self.assertIsNone(revised.value.option_parts)
        self.assertEqual(approvals.read_snapshot("qv-synth-rev").stem_parts, current.stem_parts)  # type: ignore[union-attr]


def _bars(rules: tuple[object, ...]) -> list[object]:
    return [rule for rule in rules if rule.y1 == rule.y2]  # type: ignore[attr-defined]


def _row_text(rows: tuple[object, ...] | list[object]) -> list[str]:
    return ["".join(glyph.text for glyph in row.glyphs) for row in rows]  # type: ignore[attr-defined]


def _assert_no_controls(case: unittest.TestCase, rows: tuple[object, ...] | list[object]) -> None:
    for row in rows:
        for glyph in row.glyphs:  # type: ignore[attr-defined]
            case.assertTrue(glyph.text)
            case.assertTrue(all(ord(char) >= 32 for char in glyph.text))


def _row_needs_face(row: tuple[object, ...]) -> bool:
    if len(row) > 4 and row[4] == "cjk":
        return True
    return any("\u4e00" <= char <= "\u9fff" for char in str(row[0]))


def _glyph(box: object, text: str) -> object:
    found = [glyph for glyph in box.glyphs if glyph.text == text]  # type: ignore[attr-defined]
    if not found:
        raise AssertionError(text)
    return found[0]


def _item(
    stem: str,
    question_version_id: str = "qv-synth-sqrt",
    *,
    order: int = 1,
    stem_parts: tuple[tuple[str, str], ...] | None = None,
    option_parts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None = None,
) -> PracticeItem:
    return PracticeItem(
        paper_id="paper-synth-formula",
        order_no=order,
        question_version_id=question_version_id,
        answer_version_id="av-" + question_version_id[3:],
        stem_text=stem,
        stem_parts=stem_parts,
        option_parts=option_parts,
    )


def _snapshot(
    question_version_id: str,
    stem: str,
    stem_parts: tuple[tuple[str, str], ...] | None,
    option_parts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None,
) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=question_version_id,
        answer_version_id="av-" + question_version_id[3:],
        asset_ids=(),
        layout_template_id="",
        question_approved=True,
        answer_approved=True,
        retired=False,
        subject_id="math",
        item_order=("sq-1",),
        stem=stem,
        answer_text="1",
        type="fill_blank",
        structure="fill",
        stem_parts=stem_parts,
        option_parts=option_parts,
    )


class _Writer:
    def __init__(self) -> None:
        self.called = False

    def place_composed(self, paper: Paper, items: tuple[PracticeItem, ...]) -> None:
        self.called = True


class _Publications:
    def active_of(self, question_version_id: str, answer_version_id: str) -> object:
        return object()


class _Approvals:
    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot:
        return replace(
            _snapshot(question_version_id, r"\frac{1}{2}", None, None),
            question_approved=True,
            answer_approved=True,
        )
