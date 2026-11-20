"""Ports for the knowledge slice. Adapters implement these. No driver types.

KnowledgePoints, Methods, and QuestionTagger are the three ports.
CatalogReader is the read-only seam. Catalog implements it without importing
this package. A missing, unapproved, retired, or subject-less version is None.

Refusal tokens on KnowledgeFault:
- invalid: blank id, blank subject_id, or blank display_name
- duplicate: the id, or the same link, is already stored
- not_found: the point or method id is unknown
- referenced: a question still cites this id
- not_approved: CatalogReader.approved returned None
- invalid_role: role is neither primary nor support
- primary_taken: this question version already has one primary
- support_only: a composite version was given role primary
- subject_mismatch: the question subject and the catalog subject differ

chapter_name may be blank. A second method on the same version is allowed.
Methods are allowed on all structures. An approved version with no tags is
absent from versions_for_point. MemoryTagger is constructed with
KnowledgePoints, Methods, and CatalogReader.
"""

from __future__ import annotations

from typing import Protocol

from backend.knowledge.models import (
    ApprovedQuestion,
    KnowledgePoint,
    Method,
    QuestionKnowledge,
    QuestionMethod,
)


class KnowledgePoints(Protocol):
    def insert(self, point: KnowledgePoint) -> None:
        """Store one point."""

    def rename(self, knowledge_point_id: str, display_name: str, chapter_name: str) -> None:
        """Replace the display name and the chapter name. The id and subject stay."""

    def remove(self, knowledge_point_id: str) -> None:
        """Delete a point that no question still cites."""

    def by_id(self, knowledge_point_id: str) -> KnowledgePoint | None:
        """Return the point, or None when the id is unknown."""


class Methods(Protocol):
    def insert(self, method: Method) -> None:
        """Store one method."""

    def rename(self, method_id: str, display_name: str) -> None:
        """Replace the display name. The id and subject stay."""

    def remove(self, method_id: str) -> None:
        """Delete a method that no question still cites."""

    def by_id(self, method_id: str) -> Method | None:
        """Return the method, or None when the id is unknown."""


class QuestionTagger(Protocol):
    def tag_point(self, link: QuestionKnowledge) -> None:
        """Cite one confirmed point. At most one primary. Composite stays support."""

    def tag_method(self, link: QuestionMethod) -> None:
        """Cite one confirmed method. Methods are allowed on all structures. No rank."""

    def points_on(self, question_version_id: str) -> tuple[QuestionKnowledge, ...]:
        """Links on this version, in the order they were stored."""

    def methods_on(self, question_version_id: str) -> tuple[QuestionMethod, ...]:
        """Links on this version, in the order they were stored."""

    def versions_for_point(self, knowledge_point_id: str) -> tuple[str, ...]:
        """Approved versions that cite this point. Untagged versions are absent."""


class CatalogReader(Protocol):
    def approved(self, question_version_id: str) -> ApprovedQuestion | None:
        """The approved question, or None when it must not be tagged."""
