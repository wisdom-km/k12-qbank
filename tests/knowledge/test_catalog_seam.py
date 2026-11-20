"""Tags require an approved catalog version. The shell does not import knowledge."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from backend.knowledge.memory import MemoryKnowledgePoints, MemoryMethods, MemoryTagger
from tests.knowledge.world import SUBJECT, Bank, fault_code, reader_with, snapshot


ROOT = Path(__file__).resolve().parents[2]


class CatalogSeamTest(unittest.TestCase):
    def test_missing_and_unapproved_versions_are_not_approved(self) -> None:
        reader = reader_with(snapshot("q-draft", question_approved=False))
        bank = Bank(reader)
        bank.point("kp-1", "有理数")
        self.assertEqual(fault_code(self, lambda: bank.tag_point("q-missing", "kp-1")), "not_approved")
        self.assertEqual(fault_code(self, lambda: bank.tag_point("q-draft", "kp-1")), "not_approved")

    def test_retired_and_blank_subject_are_not_approved(self) -> None:
        reader = reader_with(
            snapshot("q-retired", retired=True),
            snapshot("q-blank", subject_id=" "),
            snapshot("q-half", answer_approved=False),
        )
        bank = Bank(reader)
        bank.point("kp-1", "有理数加法")
        for question_id in ("q-retired", "q-blank", "q-half"):
            code = fault_code(self, lambda question_id=question_id: bank.tag_point(question_id, "kp-1"))
            self.assertEqual(code, "not_approved")

    def test_an_approved_snapshot_keeps_structure_for_the_composite_rule(self) -> None:
        reader = reader_with(
            snapshot("q-composite", structure="composite", question_type="composite"),
            snapshot("q-open", structure="worked"),
        )
        approved = reader.approved("q-composite")
        self.assertIsNotNone(approved)
        assert approved is not None
        self.assertEqual(approved.structure, "composite")
        self.assertEqual(approved.subject_id, SUBJECT)
        bank = Bank(reader)
        bank.point("kp-1", "同号相加", "第一章")
        self.assertEqual(fault_code(self, lambda: bank.tag_point("q-composite", "kp-1", "primary")), "support_only")
        bank.tag_point("q-composite", "kp-1", "support")
        self.assertEqual(bank.tagger.versions_for_point("kp-1"), ("q-composite",))
        self.assertNotIn("q-open", bank.tagger.versions_for_point("kp-1"))

    def test_catalog_reader_does_not_import_knowledge(self) -> None:
        path = ROOT / "backend" / "catalog" / "application" / "approved_question.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertFalse(any(name.startswith("backend.knowledge") for name in imported))
        tagger = MemoryTagger(MemoryKnowledgePoints(), MemoryMethods(), reader_with())
        self.assertIsNotNone(tagger)
