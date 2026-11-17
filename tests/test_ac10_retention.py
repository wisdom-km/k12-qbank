"""AC-10: retention is recorded, and no retention period is invented."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Ac10RetentionDocsTest(unittest.TestCase):
    def test_ac10_names_three_classes_and_leaves_the_period_open(self) -> None:
        prd = (ROOT / "PRD.md").read_text(encoding="utf-8")
        adr = (ROOT / "docs" / "adr" / "0020-learning-data-retention.md").read_text(encoding="utf-8")
        logging = (ROOT / "docs" / "adr" / "0008-logging.md").read_text(encoding="utf-8")
        index = (ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")

        self.assertIn("US-12", prd)
        self.assertIn("AC-10", prd)
        self.assertIn(
            "| DEC-03 | 材料及样本使用范围、外部供应商、遮挡、留存和备份规则 | 机构负责人 | 真实学生试用前，也在调用真实模型之前 |",
            prd,
        )
        self.assertIn("状态：accepted", adr)
        self.assertIn("待定标", adr)
        self.assertIn("照片、作答记录和建议", adr)
        self.assertNotRegex(adr, r"\d+\s*天")
        self.assertNotRegex(adr, r"\d+\s*个月")
        self.assertIn("保留多久、谁可以看，等 DEC-03。", logging)
        self.assertIn("采纳。2026-11-14。保留期限待定标。", logging)
        self.assertIn("| [0020](0020-learning-data-retention.md) | 学情保留和删除 | accepted |", index)
        self.assertIsNone(re.search(r"DEC-0[1-6]\s*[:：]\s*\d+", adr))
