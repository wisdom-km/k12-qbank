"""Shared memory world for knowledge tests."""

from __future__ import annotations

import unittest

from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.application.approved_question import ApprovedQuestionReader
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.knowledge.memory import MemoryKnowledgePoints, MemoryMethods, MemoryTagger
from backend.knowledge.models import (
    PRIMARY,
    SUPPORT,
    ApprovedQuestion,
    KnowledgeFault,
    KnowledgePoint,
    Method,
    QuestionKnowledge,
    QuestionMethod,
)

SUBJECT = "math"
OTHER = "chinese"


def fault_code(test: unittest.TestCase, call) -> str:
    with test.assertRaises(KnowledgeFault) as caught:
        call()
    err = caught.exception
    test.assertEqual(str(err), err.code)
    test.assertIsInstance(err.message, str)
    return err.code


class Listing:
    """In-memory catalog of already approved questions."""

    def __init__(self) -> None:
        self._rows: dict[str, ApprovedQuestion] = {}

    def add(self, question_version_id: str, structure: str, subject_id: str = SUBJECT) -> None:
        self._rows[question_version_id] = ApprovedQuestion(
            question_version_id=question_version_id,
            subject_id=subject_id,
            structure=structure,
        )

    def approved(self, question_version_id: str) -> ApprovedQuestion | None:
        return self._rows.get(question_version_id)


class Bank:
    def __init__(self, catalog: Listing | ApprovedQuestionReader | None = None) -> None:
        self.points = MemoryKnowledgePoints()
        self.methods = MemoryMethods()
        self._listing = Listing() if catalog is None else None
        self.catalog = self._listing if self._listing is not None else catalog
        assert self.catalog is not None
        self.tagger = MemoryTagger(self.points, self.methods, self.catalog)

    def add_question(self, question_version_id: str, structure: str, subject_id: str = SUBJECT) -> None:
        if self._listing is None:
            raise RuntimeError("this bank uses a fixed catalog reader")
        self._listing.add(question_version_id, structure, subject_id)

    def point(self, point_id: str, name: str, chapter: str = "", subject_id: str = SUBJECT) -> KnowledgePoint:
        row = KnowledgePoint(point_id, subject_id, name, chapter)
        self.points.insert(row)
        return row

    def method(self, method_id: str, name: str, subject_id: str = SUBJECT) -> Method:
        row = Method(method_id, subject_id, name)
        self.methods.insert(row)
        return row

    def tag_point(self, question_version_id: str, point_id: str, role: str = SUPPORT) -> None:
        self.tagger.tag_point(QuestionKnowledge(question_version_id, point_id, role))

    def tag_method(self, question_version_id: str, method_id: str) -> None:
        self.tagger.tag_method(QuestionMethod(question_version_id, method_id))


def snapshot(
    question_version_id: str,
    *,
    subject_id: str = SUBJECT,
    structure: str = "worked",
    question_type: str = "solution",
    question_approved: bool = True,
    answer_approved: bool = True,
    retired: bool = False,
) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        question_version_id=question_version_id,
        answer_version_id=question_version_id + "-a",
        asset_ids=(),
        layout_template_id="layout-1",
        question_approved=question_approved,
        answer_approved=answer_approved,
        retired=retired,
        subject_id=subject_id,
        type=question_type,
        structure=structure,
    )


def reader_with(*rows: ApprovalSnapshot) -> ApprovedQuestionReader:
    approvals = MemoryApprovals()
    for row in rows:
        approvals.put(row)
    return ApprovedQuestionReader(approvals)


__all__ = [
    "OTHER",
    "PRIMARY",
    "SUBJECT",
    "SUPPORT",
    "Bank",
    "fault_code",
    "reader_with",
    "snapshot",
]
