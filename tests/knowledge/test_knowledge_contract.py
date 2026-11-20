"""Memory contract for the knowledge ports.

PostgreSQL is reserved for the first real knowledge write. That later batch
owns V006 and a second adapter. This file does not read K12_PG_DSN, and CI
must not apply a knowledge migration. The cases below run on memory every time.
"""

from __future__ import annotations

import unittest

from backend.knowledge.models import FAULT_CODES, KnowledgeFault
from tests.knowledge.world import SUBJECT, Bank


class KnowledgeContract:
    """Cases a later adapter must keep. Memory binds them in MemoryKnowledgeContract."""

    bank: Bank

    def tag_same_subject_point_and_method(self) -> None:
        self.bank.add_question("q-1", "worked")
        self.bank.point("kp-1", "有理数", "第一章")
        self.bank.method("m-1", "移项")
        self.bank.tag_point("q-1", "kp-1", "primary")
        self.bank.tag_method("q-1", "m-1")
        self.assertEqual(self.bank.tagger.versions_for_point("kp-1"), ("q-1",))
        found = self.bank.points.by_id("kp-1")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.subject_id, SUBJECT)


class MemoryKnowledgeContract(KnowledgeContract, unittest.TestCase):
    def setUp(self) -> None:
        self.bank = Bank()

    def test_memory_adapter_stores_a_confirmed_tag(self) -> None:
        self.tag_same_subject_point_and_method()

    def test_fault_matches_code_and_keeps_message_off_the_token(self) -> None:
        err = KnowledgeFault("not_approved", "for logs only")
        self.assertIn(err.code, FAULT_CODES)
        self.assertEqual(str(err), "not_approved")
        self.assertEqual(err.message, "for logs only")
        self.assertNotIn("for logs only", str(err))
