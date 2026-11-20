"""Tag rules from ADR 0015 and ADR 0016, plus subject match."""

from __future__ import annotations

import unittest

from backend.knowledge.models import FAULT_CODES, QuestionKnowledge
from tests.knowledge.world import OTHER, PRIMARY, SUBJECT, SUPPORT, Bank, fault_code


class TaggerRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bank = Bank()
        self.bank.add_question("q-choice", "choice")
        self.bank.add_question("q-composite", "composite")
        self.bank.add_question("q-open", "worked")
        self.bank.point("kp-main", "有理数", "第一章")
        self.bank.point("kp-add", "有理数加法", "第一章")
        self.bank.point("kp-same", "同号相加", "第一章")
        self.bank.point("kp-other", "异号相加", "第一章", OTHER)
        self.bank.method("m-drop", "去括号")
        self.bank.method("m-common", "通分")
        self.bank.method("m-move", "移项")
        self.bank.method("m-other", "去括号", OTHER)

    def test_a_second_primary_is_refused(self) -> None:
        self.bank.tag_point("q-choice", "kp-main", PRIMARY)
        self.bank.tag_point("q-choice", "kp-add", SUPPORT)
        self.assertEqual(
            fault_code(self, lambda: self.bank.tag_point("q-choice", "kp-same", PRIMARY)),
            "primary_taken",
        )
        self.assertEqual(
            [link.knowledge_point_id for link in self.bank.tagger.points_on("q-choice")],
            ["kp-main", "kp-add"],
        )

    def test_composite_primary_is_refused_and_support_is_kept(self) -> None:
        self.assertEqual(
            fault_code(self, lambda: self.bank.tag_point("q-composite", "kp-main", PRIMARY)),
            "support_only",
        )
        self.bank.tag_point("q-composite", "kp-add", SUPPORT)
        self.bank.tag_point("q-composite", "kp-same", SUPPORT)
        roles = [link.role for link in self.bank.tagger.points_on("q-composite")]
        self.assertEqual(roles, [SUPPORT, SUPPORT])

    def test_an_untagged_approved_question_stays_out_of_search(self) -> None:
        self.bank.tag_point("q-choice", "kp-main", PRIMARY)
        found = self.bank.tagger.versions_for_point("kp-main")
        self.assertEqual(found, ("q-choice",))
        self.assertNotIn("q-open", found)
        self.assertEqual(self.bank.tagger.points_on("q-open"), ())

    def test_several_methods_on_one_question_have_no_rank(self) -> None:
        self.bank.tag_method("q-composite", "m-drop")
        self.bank.tag_method("q-composite", "m-common")
        self.bank.tag_method("q-choice", "m-move")
        linked = self.bank.tagger.methods_on("q-composite")
        self.assertEqual([link.method_id for link in linked], ["m-drop", "m-common"])

    def test_subject_mismatch_on_point(self) -> None:
        code = fault_code(self, lambda: self.bank.tag_point("q-choice", "kp-other", SUPPORT))
        self.assertEqual(code, "subject_mismatch")
        self.assertIn(code, FAULT_CODES)
        self.assertEqual(self.bank.tagger.points_on("q-choice"), ())

    def test_subject_mismatch_on_method(self) -> None:
        code = fault_code(self, lambda: self.bank.tag_method("q-composite", "m-other"))
        self.assertEqual(code, "subject_mismatch")
        self.assertEqual(self.bank.tagger.methods_on("q-composite"), ())

    def test_duplicate_link_and_invalid_role(self) -> None:
        self.bank.tag_point("q-choice", "kp-main", PRIMARY)
        self.assertEqual(
            fault_code(self, lambda: self.bank.tag_point("q-choice", "kp-main", SUPPORT)),
            "duplicate",
        )
        bad = QuestionKnowledge("q-choice", "kp-add", "main")
        self.assertEqual(fault_code(self, lambda: self.bank.tagger.tag_point(bad)), "invalid_role")
