"""Knowledge catalog records. Plain data. No database types.

Columns follow ADR 0015 and ADR 0016. A display name is a teacher-confirmed
label. This module has no suggestion field and no model-origin field.
"""

from __future__ import annotations

from dataclasses import dataclass

PRIMARY = "primary"
SUPPORT = "support"
ROLES = frozenset({PRIMARY, SUPPORT})
COMPOSITE = "composite"
FAULT_CODES = frozenset({
    "invalid",
    "duplicate",
    "not_found",
    "referenced",
    "not_approved",
    "invalid_role",
    "primary_taken",
    "support_only",
    "subject_mismatch",
})


@dataclass(frozen=True)
class KnowledgePoint:
    knowledge_point_id: str
    subject_id: str
    display_name: str
    chapter_name: str


@dataclass(frozen=True)
class Method:
    method_id: str
    subject_id: str
    display_name: str


@dataclass(frozen=True)
class QuestionKnowledge:
    question_version_id: str
    knowledge_point_id: str
    role: str


@dataclass(frozen=True)
class QuestionMethod:
    question_version_id: str
    method_id: str


@dataclass(frozen=True)
class ApprovedQuestion:
    """One approved catalog question a tag may cite.

    structure is how the tagger tells a composite version from any other.
    It is not a column of question_knowledge.
    """

    question_version_id: str
    subject_id: str
    structure: str


class KnowledgeFault(Exception):
    """Business refusal, same shape as identity's Conflict.

    Callers match .code. The exception text is that code.
    .message is optional log text and is not an API body.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.message = message
