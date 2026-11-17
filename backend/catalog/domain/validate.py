"""Question-draft contract shared with the review tool. Not a publication.

A crop is four coordinates. Editable geometry is accepted only as a reserved
document and is not interpreted here. The file walk lives in parse.py.
Nothing in this module opens a database.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.kernel.result import Err

CONTRACT = "k12-question-draft"
CONTRACT_VERSION = 1
GEOMETRY_KIND = "editable-geometry"
# Pedagogical codes reuse a structure. Add a code here before accepting it.
TYPE_STRUCTURE = {
    "single_choice": "choice",
    "multiple_choice": "choice",
    "fill_blank": "blank",
    "solution": "worked",
    "unresolved": "unresolved",
    "composite": "composite",
}
TYPES = set(TYPE_STRUCTURE)
PART_STRUCTURES = {"choice", "blank", "worked"}
STATUSES = {"candidate", "needs_confirm", "confirmed"}
FILE_KEYS = {
    "contract",
    "contract_version",
    "schema_version",
    "ok",
    "reason",
    "preface",
    "source",
    "questions",
}
QUESTION_KEYS = {
    "key",
    "section",
    "number",
    "type",
    "structure",
    "status",
    "stem",
    "options",
    "subquestions",
    "assets",
    "geometry",
}


@dataclass(frozen=True)
class TextPart:
    value: str


@dataclass(frozen=True)
class MathPart:
    latex: str


@dataclass(frozen=True)
class ChoiceOption:
    key: str
    content: tuple[TextPart | MathPart, ...]


@dataclass(frozen=True)
class SubQuestion:
    number: str
    stem: tuple[TextPart | MathPart, ...]
    type: str | None = None
    structure: str | None = None
    options: tuple[ChoiceOption, ...] = ()


@dataclass(frozen=True)
class CropAsset:
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class GeometrySlot:
    """Reserved for a later figure_geometry row. document_json is not read."""

    version: int
    document_json: str


@dataclass(frozen=True)
class QuestionDraft:
    key: str
    section: str
    number: str
    type: str
    structure: str
    status: str
    stem: tuple[TextPart | MathPart, ...]
    options: tuple[ChoiceOption, ...]
    subquestions: tuple[SubQuestion, ...]
    assets: tuple[CropAsset, ...]
    geometry: GeometrySlot | None


@dataclass(frozen=True)
class DraftFile:
    pdf_page: int | None
    ok: bool
    reason: str
    preface: str
    questions: tuple[QuestionDraft, ...]


def publication_blocked(draft: QuestionDraft) -> Err:
    """A draft never becomes a publication, even after the teacher sets a type."""
    if not draft.key.strip():
        return Err("not_draft", "a question draft needs a key")
    return Err("draft", "a question draft is not a publication")

