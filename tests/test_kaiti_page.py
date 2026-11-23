"""AC-02: Chinese on the synthetic page uses the installed face. The font file stays out of the repo."""

from __future__ import annotations

import struct
import unittest
from pathlib import Path

from backend.kernel.result import Err
from backend.practice.adapters.pdf_font import _face_origin, load_system_face
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.domain.page_face import PaperPage

ROOT = Path(__file__).resolve().parents[1]
_MESSAGE = "this synthetic page cannot encode the formula"
def _installed_face() -> str | None:
    face = load_system_face()
    if face is None:
        return None
    return face.name


def _page(formula: str) -> PaperPage:
    return PaperPage(
        question_version_id="q-v1",
        answer_version_id="a-v1",
        formula=formula,
        student_id="student-synth",
        page_number=1,
        item_order=("sq-1",),
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        paper_id="paper-1",
        page_count=1,
    )


def _embedded_ttf(pdf: bytes) -> bytes:
    marker = pdf.index(b"/Length1 ")
    length = int(pdf[marker + len(b"/Length1 ") : pdf.index(b" >>", marker)])
    start = pdf.index(b"stream\n", marker) + len(b"stream\n")
    return pdf[start : start + length]


def _cmap_glyph(ttf: bytes, code: int) -> int:
    count = struct.unpack_from(">H", ttf, 4)[0]
    cmap = b""
    for index in range(count):
        tag, _checksum, start, length = struct.unpack_from(">4sIII", ttf, 12 + index * 16)
        if tag == b"cmap":
            cmap = ttf[start : start + length]
    _platform, _encoding, offset = struct.unpack_from(">HHI", cmap, 4)
    seg_count = struct.unpack_from(">H", cmap, offset + 6)[0] // 2
    end_at = offset + 14
    start_at = end_at + seg_count * 2 + 2
    delta_at = start_at + seg_count * 2
    for index in range(seg_count):
        end = struct.unpack_from(">H", cmap, end_at + index * 2)[0]
        if code > end:
            continue
        start = struct.unpack_from(">H", cmap, start_at + index * 2)[0]
        delta = struct.unpack_from(">H", cmap, delta_at + index * 2)[0]
        if start <= code <= end:
            return (code + delta) & 0xFFFF
        return 0
    return 0


class KaitiPageTest(unittest.TestCase):
    def test_chinese_formula_uses_the_installed_face_when_one_is_present(self) -> None:
        drawn = StdPdf().render(_page("解："))
        face = _installed_face()
        if face is None:
            self.assertIsInstance(drawn, Err)
            assert isinstance(drawn, Err)
            self.assertEqual(drawn.code, "pdf_font_missing")
            return
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        self.assertLess(len(drawn), 300_000)
        self.assertIn(b"/BaseFont /Helvetica", drawn)
        self.assertIn(b"/Encoding /WinAnsiEncoding", drawn)
        self.assertIn(f"/BaseFont /K12QBK+{face}".encode("ascii"), drawn)
        self.assertIn(b"/FontFile2", drawn)
        if "Noto" not in face:
            self.assertNotIn(b"Noto", drawn)
        ttf = _embedded_ttf(drawn)
        self.assertEqual(ttf[:4], b"\x00\x01\x00\x00")
        glyph = _cmap_glyph(ttf, ord("解"))
        self.assertGreater(glyph, 0)
        self.assertIn(f"{glyph:04X}".encode("ascii"), drawn)

    def test_times_sign_stays_helvetica_and_radical_stays_waiting(self) -> None:
        drawn = StdPdf().render(_page("2\u00d73"))
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        self.assertIn(b"/Encoding /WinAnsiEncoding", drawn)
        self.assertIn("formula 2\u00d73".encode("cp1252"), drawn)
        self.assertNotIn(b"/FontFile2", drawn)
        self.assertNotIn(b"K12QBK+", drawn)
        refused = StdPdf().render(_page("\u221a2"))
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertEqual(refused.code, "not_rendered")
        self.assertEqual(refused.message, _MESSAGE)

    def test_adr_0024_is_accepted_while_0022_stays_proposed(self) -> None:
        adopted = (ROOT / "docs" / "adr" / "0024-system-kaiti.md").read_text(encoding="utf-8")
        waiting = (ROOT / "docs" / "adr" / "0022-cjk-font-license.md").read_text(encoding="utf-8")
        self.assertIn("状态：accepted", adopted)
        self.assertIn("状态：proposed", waiting)
        self.assertIn("需要人工决定", waiting)
        self.assertFalse(any(ROOT.rglob("*.ttf")))
        self.assertFalse(any(ROOT.rglob("*.otf")))

    def test_a_collection_header_points_at_the_first_face(self) -> None:
        data = b"ttcf" + struct.pack(">II", 0x00010000, 1) + struct.pack(">I", 0x1234)
        self.assertEqual(_face_origin(data), 0x1234)
        self.assertEqual(_face_origin(b"\x00\x01\x00\x00"), 0)
        self.assertIsNone(_face_origin(b"OTTO"))
