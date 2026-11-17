"""Synthetic PDF stays on the built-in Helvetica contract until a person accepts a font license."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HelveticaFontContractTest(unittest.TestCase):
    def test_helvetica_contract_stays_while_the_cjk_license_needs_a_person(self) -> None:
        adr = (ROOT / "docs" / "adr" / "0022-cjk-font-license.md").read_text(encoding="utf-8")
        page = (ROOT / "backend" / "practice" / "adapters" / "pdf_page.py").read_text(encoding="utf-8")
        index = (ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
        deps = (ROOT / "docs" / "dependencies.md").read_text(encoding="utf-8")

        self.assertIn("状态：proposed", adr)
        self.assertIn("需要人工决定", adr)
        self.assertIn("SIL Open Font License, Version 1.1", adr)
        self.assertIn("/BaseFont /Helvetica", page)
        self.assertNotIn("Noto", page)
        self.assertIn("合成 PDF 仍由标准库写成一页 Helvetica", deps)
        self.assertIn("| [0022](0022-cjk-font-license.md) | 中文字体许可证 | proposed |", index)
        self.assertFalse(any(ROOT.rglob("*.otf")))
        self.assertFalse(any(ROOT.rglob("*.ttf")))
