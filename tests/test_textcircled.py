"""Circled numbers 1 through 20 lay out as glyphs. A missing glyph is an error."""

from __future__ import annotations

import unittest

from backend.practice.adapters.pdf_font import PageFont
from backend.practice.adapters.pdf_page import _glyph_hex
from backend.practice.domain.formula import FormulaFault, layout_math, unsupported_commands

_SIZE = 12.0


class TextCircledTest(unittest.TestCase):
    def test_one_through_twenty_become_circled_digits(self) -> None:
        self.assertEqual(unsupported_commands(r"\textcircled{1}"), ())
        for number in range(1, 21):
            box = layout_math(r"\textcircled{" + str(number) + "}", _SIZE)
            self.assertEqual([glyph.text for glyph in box.glyphs], [chr(0x2460 + number - 1)])
            self.assertEqual(box.glyphs[0].font, "cjk")

    def test_out_of_range_and_a_missing_glyph_fail(self) -> None:
        for latex in (r"\textcircled{0}", r"\textcircled{21}", r"\textcircled{a}", r"\textcircled{}"):
            with self.assertRaises(FormulaFault) as caught:
                layout_math(latex, _SIZE)
            self.assertEqual(caught.exception.code, "formula_unsupported")
            self.assertEqual(caught.exception.command, r"\textcircled")
        font = PageFont("synth", b"", {}, {}, (0, 0, 0, 0), 0, 0)
        with self.assertRaises(UnicodeEncodeError):
            _glyph_hex("\u2460", font)
        present = PageFont("synth", b"", {0x2460: 5}, {}, (0, 0, 0, 0), 0, 0)
        self.assertEqual(_glyph_hex("\u2460", present), "0005")
