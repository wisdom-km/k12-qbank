"""Create, rename, and refuse to delete a cited method."""

from __future__ import annotations

import unittest

from backend.knowledge.models import Method
from tests.knowledge.world import SUBJECT, Bank, fault_code


class MethodCrudTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bank = Bank()
        self.bank.add_question("q-1", "worked")

    def test_insert_rename_and_keep_the_subject(self) -> None:
        self.bank.method("m-1", "去括号")
        self.bank.methods.rename("m-1", "通分")
        row = self.bank.methods.by_id("m-1")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.display_name, "通分")
        self.assertEqual(row.subject_id, SUBJECT)

    def test_blank_display_name_is_invalid(self) -> None:
        self.assertEqual(
            fault_code(self, lambda: self.bank.methods.insert(Method("m-x", SUBJECT, ""))),
            "invalid",
        )
        self.bank.method("m-1", "移项")
        self.assertEqual(fault_code(self, lambda: self.bank.methods.rename("m-1", " ")), "invalid")

    def test_duplicate_id_and_missing_id(self) -> None:
        self.bank.method("m-1", "去括号")
        self.assertEqual(fault_code(self, lambda: self.bank.method("m-1", "通分")), "duplicate")
        self.assertEqual(fault_code(self, lambda: self.bank.methods.remove("missing")), "not_found")

    def test_remove_refuses_a_cited_method_and_allows_an_unused_one(self) -> None:
        self.bank.method("m-1", "去括号")
        self.bank.method("m-2", "移项")
        self.bank.tag_method("q-1", "m-1")
        self.assertEqual(fault_code(self, lambda: self.bank.methods.remove("m-1")), "referenced")
        self.bank.methods.remove("m-2")
        self.assertIsNone(self.bank.methods.by_id("m-2"))
