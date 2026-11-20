"""In-memory knowledge catalog. No database and no suggestion rows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from backend.knowledge.models import (
    COMPOSITE,
    PRIMARY,
    ROLES,
    ApprovedQuestion,
    KnowledgeFault,
    KnowledgePoint,
    Method,
    QuestionKnowledge,
    QuestionMethod,
)
from backend.knowledge.ports import CatalogReader, KnowledgePoints, Methods


def _blank(value: str) -> bool:
    return value.strip() == ""


def _refuse_blank(*values: str) -> None:
    if any(_blank(value) for value in values):
        raise KnowledgeFault("invalid")


class MemoryKnowledgePoints:
    def __init__(self) -> None:
        self._rows: dict[str, KnowledgePoint] = {}
        self._cited: Callable[[str], bool] = lambda _point_id: False

    def watch(self, cited: Callable[[str], bool]) -> None:
        """Remember which points a tagger still cites. Not a port method."""
        self._cited = cited

    def insert(self, point: KnowledgePoint) -> None:
        _refuse_blank(point.knowledge_point_id, point.subject_id, point.display_name)
        if point.knowledge_point_id in self._rows:
            raise KnowledgeFault("duplicate")
        self._rows[point.knowledge_point_id] = point

    def rename(self, knowledge_point_id: str, display_name: str, chapter_name: str) -> None:
        current = self._rows.get(knowledge_point_id)
        if current is None:
            raise KnowledgeFault("not_found")
        _refuse_blank(display_name)
        self._rows[knowledge_point_id] = replace(
            current,
            display_name=display_name,
            chapter_name=chapter_name,
        )

    def remove(self, knowledge_point_id: str) -> None:
        if knowledge_point_id not in self._rows:
            raise KnowledgeFault("not_found")
        if self._cited(knowledge_point_id):
            raise KnowledgeFault("referenced")
        del self._rows[knowledge_point_id]

    def by_id(self, knowledge_point_id: str) -> KnowledgePoint | None:
        return self._rows.get(knowledge_point_id)


class MemoryMethods:
    def __init__(self) -> None:
        self._rows: dict[str, Method] = {}
        self._cited: Callable[[str], bool] = lambda _method_id: False

    def watch(self, cited: Callable[[str], bool]) -> None:
        """Remember which methods a tagger still cites. Not a port method."""
        self._cited = cited

    def insert(self, method: Method) -> None:
        _refuse_blank(method.method_id, method.subject_id, method.display_name)
        if method.method_id in self._rows:
            raise KnowledgeFault("duplicate")
        self._rows[method.method_id] = method

    def rename(self, method_id: str, display_name: str) -> None:
        current = self._rows.get(method_id)
        if current is None:
            raise KnowledgeFault("not_found")
        _refuse_blank(display_name)
        self._rows[method_id] = replace(current, display_name=display_name)

    def remove(self, method_id: str) -> None:
        if method_id not in self._rows:
            raise KnowledgeFault("not_found")
        if self._cited(method_id):
            raise KnowledgeFault("referenced")
        del self._rows[method_id]

    def by_id(self, method_id: str) -> Method | None:
        return self._rows.get(method_id)


class MemoryTagger:
    """Tags confirmed labels. Constructed with the three read ports it queries."""

    def __init__(self, points: KnowledgePoints, methods: Methods, catalog: CatalogReader) -> None:
        self._points = points
        self._methods = methods
        self._catalog = catalog
        self._point_links: list[QuestionKnowledge] = []
        self._method_links: list[QuestionMethod] = []
        watch_points = getattr(points, "watch", None)
        watch_methods = getattr(methods, "watch", None)
        if watch_points is not None:
            watch_points(self._point_cited)
        if watch_methods is not None:
            watch_methods(self._method_cited)

    def tag_point(self, link: QuestionKnowledge) -> None:
        if link.role not in ROLES:
            raise KnowledgeFault("invalid_role")
        approved = self._catalog.approved(link.question_version_id)
        point = self._points.by_id(link.knowledge_point_id)
        self._accept_point(link, approved, point)
        self._point_links.append(link)

    def tag_method(self, link: QuestionMethod) -> None:
        approved = self._catalog.approved(link.question_version_id)
        method = self._methods.by_id(link.method_id)
        if approved is None:
            raise KnowledgeFault("not_approved")
        if method is None:
            raise KnowledgeFault("not_found")
        if approved.subject_id != method.subject_id:
            raise KnowledgeFault("subject_mismatch")
        if _method_pair(self._method_links, link):
            raise KnowledgeFault("duplicate")
        self._method_links.append(link)

    def points_on(self, question_version_id: str) -> tuple[QuestionKnowledge, ...]:
        return tuple(link for link in self._point_links if link.question_version_id == question_version_id)

    def methods_on(self, question_version_id: str) -> tuple[QuestionMethod, ...]:
        return tuple(link for link in self._method_links if link.question_version_id == question_version_id)

    def versions_for_point(self, knowledge_point_id: str) -> tuple[str, ...]:
        seen: list[str] = []
        for link in self._point_links:
            if link.knowledge_point_id != knowledge_point_id:
                continue
            if link.question_version_id not in seen:
                seen.append(link.question_version_id)
        return tuple(seen)

    def _accept_point(
        self,
        link: QuestionKnowledge,
        approved: ApprovedQuestion | None,
        point: KnowledgePoint | None,
    ) -> None:
        if approved is None:
            raise KnowledgeFault("not_approved")
        if point is None:
            raise KnowledgeFault("not_found")
        if approved.subject_id != point.subject_id:
            raise KnowledgeFault("subject_mismatch")
        if _point_pair(self._point_links, link):
            raise KnowledgeFault("duplicate")
        if link.role == PRIMARY and approved.structure == COMPOSITE:
            raise KnowledgeFault("support_only")
        if link.role == PRIMARY and _has_primary(self._point_links, link.question_version_id):
            raise KnowledgeFault("primary_taken")

    def _point_cited(self, knowledge_point_id: str) -> bool:
        return any(link.knowledge_point_id == knowledge_point_id for link in self._point_links)

    def _method_cited(self, method_id: str) -> bool:
        return any(link.method_id == method_id for link in self._method_links)


def _point_pair(links: list[QuestionKnowledge], link: QuestionKnowledge) -> bool:
    return any(
        item.question_version_id == link.question_version_id
        and item.knowledge_point_id == link.knowledge_point_id
        for item in links
    )


def _method_pair(links: list[QuestionMethod], link: QuestionMethod) -> bool:
    return any(
        item.question_version_id == link.question_version_id and item.method_id == link.method_id
        for item in links
    )


def _has_primary(links: list[QuestionKnowledge], question_version_id: str) -> bool:
    return any(item.question_version_id == question_version_id and item.role == PRIMARY for item in links)
