"""Create, rename, and refuse to delete a cited knowledge point."""

from __future__ import annotations

import unittest

from backend.knowledge.models import KnowledgePoint
from tests.knowledge.world import SUBJECT, Bank, fault_code


class KnowledgePointCrudTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bank = Bank()
        self.bank.add_question("q-1", "worked")

    def test_insert_rename_and_keep_the_subject(self) -> None:
        self.bank.point("kp-1", "有理数", "第一章")
        self.bank.points.rename("kp-1", "有理数加法", "")
        row = self.bank.points.by_id("kp-1")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.display_name, "有理数加法")
        self.assertEqual(row.chapter_name, "")
        self.assertEqual(row.subject_id, SUBJECT)

    def test_blank_display_name_is_invalid_and_blank_chapter_is_kept(self) -> None:
        self.assertEqual(
            fault_code(self, lambda: self.bank.points.insert(KnowledgePoint("kp-x", SUBJECT, "  ", "章"))),
            "invalid",
        )
        self.bank.point("kp-1", "有理数", "")
        self.assertEqual(fault_code(self, lambda: self.bank.points.rename("kp-1", "", "章")), "invalid")
        self.assertEqual(self.bank.points.by_id("kp-1").chapter_name, "")  # type: ignore[union-attr]

    def test_duplicate_id_and_missing_id(self) -> None:
        self.bank.point("kp-1", "有理数")
        self.assertEqual(
            fault_code(self, lambda: self.bank.point("kp-1", "有理数加法")),
            "duplicate",
        )
        self.assertEqual(fault_code(self, lambda: self.bank.points.remove("missing")), "not_found")
        self.assertEqual(fault_code(self, lambda: self.bank.points.rename("missing", "有理数", "")), "not_found")

    def test_remove_refuses_a_cited_point_and_allows_an_unused_one(self) -> None:
        self.bank.point("kp-1", "有理数")
        self.bank.point("kp-2", "同号相加")
        self.bank.tag_point("q-1", "kp-1")
        self.assertEqual(fault_code(self, lambda: self.bank.points.remove("kp-1")), "referenced")
        self.assertIsNotNone(self.bank.points.by_id("kp-1"))
        self.bank.points.remove("kp-2")
        self.assertIsNone(self.bank.points.by_id("kp-2"))
