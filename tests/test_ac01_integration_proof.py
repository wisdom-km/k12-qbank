"""AC-01, AC-02, and AC-04 stay a future joint proof. This change does not connect PostgreSQL."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IntegrationProofDocsTest(unittest.TestCase):
    def test_ac01_ac02_ac04_are_required_together_and_postgres_stays_unconnected(self) -> None:
        adr = (ROOT / "docs" / "adr" / "0021-integration-proof.md").read_text(encoding="utf-8")
        matrix = (ROOT / "docs" / "implementation-matrix.md").read_text(encoding="utf-8")
        index = (ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")

        self.assertIn("状态：accepted", adr)
        self.assertIn("AC-01、AC-02、AC-04", adr)
        self.assertIn("不连接数据库", adr)
        for forbidden in ("postgresql://", "CREATE TABLE", "psycopg"):
            self.assertNotIn(forbidden, adr)
        self.assertIn("PostgreSQL 还没连接，没有迁移，也没有空表。", matrix)
        self.assertIn("| [0021](0021-integration-proof.md) | 真实阶段前要有一次集成验证 | accepted |", index)
