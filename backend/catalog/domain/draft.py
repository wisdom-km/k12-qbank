"""Question-draft contract shared with the review tool. Not a publication.

A crop is four coordinates. Editable geometry is accepted only as a reserved
document and is not interpreted here. Nothing in this module opens a database.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.catalog.domain.schema_check import (
    QUESTION_SCHEMA_ID,
    dispatched_schema,
    schema_problems,
)
from backend.kernel.result import Err, Ok

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


def parse_question_draft(payload: object) -> Ok[DraftFile] | Err:
    """Accept one draft file. A page block list is refused."""
    schema = dispatched_schema(QUESTION_SCHEMA_ID, payload)
    if isinstance(schema, str):
        return Err("not_draft", schema)
    shape = schema_problems(schema, payload)
    if shape:
        return Err("not_draft", shape[0])
    if isinstance(payload, list):
        return Err("not_draft", "a page block list is not a question draft")
    if not isinstance(payload, dict):
        return Err("not_draft", "a question draft must be an object")
    if set(payload) != FILE_KEYS:
        return Err("not_draft", "the draft file keys do not match version 1")
    version = payload["contract_version"]
    if payload["contract"] != CONTRACT or isinstance(version, bool) or version != CONTRACT_VERSION:
        return Err("not_draft", "the draft contract is not version 1")
    if not isinstance(payload["ok"], bool) or not isinstance(payload["reason"], str):
        return Err("not_draft", "ok and reason have the wrong shape")
    if not isinstance(payload["preface"], str):
        return Err("not_draft", "preface must be text")
    page = _page(payload["source"])
    if isinstance(page, Err):
        return page
    questions = _questions(payload["questions"])
    if isinstance(questions, Err):
        return questions
    if not payload["ok"] and questions:
        return Err("not_draft", "a refused page has no question drafts")
    return Ok(
        DraftFile(
            pdf_page=page,
            ok=payload["ok"],
            reason=payload["reason"],
            preface=payload["preface"],
            questions=questions,
        )
    )


def publication_blocked(draft: QuestionDraft) -> Err:
    """A draft never becomes a publication, even after the teacher sets a type."""
    if not draft.key.strip():
        return Err("not_draft", "a question draft needs a key")
    return Err("draft", "a question draft is not a publication")


def _page(source: object) -> int | None | Err:
    if not isinstance(source, dict) or set(source) != {"pdf_page"}:
        return Err("not_draft", "source must name a pdf page")
    page = source["pdf_page"]
    if page is None:
        return None
    if isinstance(page, bool) or not isinstance(page, int):
        return Err("not_draft", "pdf_page must be a whole number or empty")
    return page


def _questions(raw: object) -> tuple[QuestionDraft, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "questions must be a list")
    parsed: list[QuestionDraft] = []
    for item in raw:
        question = _question(item)
        if isinstance(question, Err):
            return question
        parsed.append(question)
    return tuple(parsed)


def _question(item: object) -> QuestionDraft | Err:
    if not isinstance(item, dict) or set(item) != QUESTION_KEYS:
        return Err("not_draft", "a question draft has the wrong fields")
    if item["type"] not in TYPES or item["status"] not in STATUSES:
        return Err("not_draft", "the question type or status is unknown")
    if item["structure"] != TYPE_STRUCTURE[item["type"]]:
        return Err("not_draft", "the question structure does not match its type")
    if not isinstance(item["key"], str) or not isinstance(item["section"], str):
        return Err("not_draft", "key and section must be text")
    if not isinstance(item["number"], str):
        return Err("not_draft", "the question number must be text")
    stem = _parts(item["stem"])
    if isinstance(stem, Err):
        return stem
    options = _options(item["options"])
    if isinstance(options, Err):
        return options
    subs = _subs(item["subquestions"], item["structure"])
    if isinstance(subs, Err):
        return subs
    if item["structure"] == "composite" and (options or len(subs) < 2):
        return Err("not_draft", "a composite question needs at least two typed parts and no options of its own")
    assets = _assets(item["assets"])
    if isinstance(assets, Err):
        return assets
    geometry = _geometry(item["geometry"])
    if isinstance(geometry, Err):
        return geometry
    return QuestionDraft(
        key=item["key"],
        section=item["section"],
        number=item["number"],
        type=item["type"],
        structure=item["structure"],
        status=item["status"],
        stem=stem,
        options=options,
        subquestions=subs,
        assets=assets,
        geometry=geometry,
    )


def _parts(raw: object) -> tuple[TextPart | MathPart, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "stem parts must be a list")
    parts: list[TextPart | MathPart] = []
    for part in raw:
        if not isinstance(part, dict):
            return Err("not_draft", "a stem part must be an object")
        if set(part) == {"type", "value"} and part["type"] == "text" and isinstance(part["value"], str):
            parts.append(TextPart(part["value"]))
            continue
        if set(part) == {"type", "latex"} and part["type"] == "math" and isinstance(part["latex"], str):
            parts.append(MathPart(part["latex"]))
            continue
        return Err("not_draft", "a stem part must be text or math")
    return tuple(parts)


def _options(raw: object) -> tuple[ChoiceOption, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "options must be a list")
    options: list[ChoiceOption] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"key", "content"}:
            return Err("not_draft", "an option needs a key and content")
        if item["key"] not in {"A", "B", "C", "D"}:
            return Err("not_draft", "an option key must be A, B, C, or D")
        content = _parts(item["content"])
        if isinstance(content, Err):
            return content
        options.append(ChoiceOption(item["key"], content))
    return tuple(options)


def _subs(raw: object, parent_structure: str) -> tuple[SubQuestion, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "subquestions must be a list")
    subs: list[SubQuestion] = []
    for item in raw:
        parsed = _sub(item, parent_structure)
        if isinstance(parsed, Err):
            return parsed
        subs.append(parsed)
    return tuple(subs)


def _sub(item: object, parent_structure: str) -> SubQuestion | Err:
    if not isinstance(item, dict):
        return Err("not_draft", "a subquestion must be an object")
    keys = set(item)
    inherited = keys == {"number", "stem"}
    typed = keys == {"number", "stem", "type", "structure"} or keys == {
        "number",
        "stem",
        "type",
        "structure",
        "options",
    }
    if not inherited and not typed:
        return Err("not_draft", "a subquestion needs a number and a stem")
    if not isinstance(item["number"], str):
        return Err("not_draft", "a subquestion number must be text")
    stem = _parts(item["stem"])
    if isinstance(stem, Err):
        return stem
    if inherited:
        if parent_structure == "composite":
            return Err("not_draft", "each part of a composite question needs its own type")
        return SubQuestion(item["number"], stem)
    part_type = item["type"]
    part_structure = item["structure"]
    if parent_structure != "composite":
        return Err("not_draft", "only a composite question gives each part a type")
    if part_type not in TYPE_STRUCTURE or TYPE_STRUCTURE[part_type] not in PART_STRUCTURES:
        return Err("not_draft", "a composite part must use an existing part shape")
    if part_structure != TYPE_STRUCTURE[part_type]:
        return Err("not_draft", "a composite part structure does not match its type")
    if part_structure == "choice":
        options = _options(item.get("options"))
        if isinstance(options, Err):
            return options
        if len(options) < 2:
            return Err("not_draft", "a choice part needs at least two options")
        return SubQuestion(item["number"], stem, part_type, part_structure, options)
    if "options" in item:
        return Err("not_draft", "only a choice part has options")
    return SubQuestion(item["number"], stem, part_type, part_structure)


def _assets(raw: object) -> tuple[CropAsset, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "assets must be a list")
    assets: list[CropAsset] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"role", "bbox"} or item["role"] != "crop":
            return Err("not_draft", "an asset must be a crop")
        bbox = item["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4 or any(not _number(value) for value in bbox):
            return Err("not_draft", "a crop needs four coordinates")
        assets.append(CropAsset(tuple(float(value) for value in bbox)))
    return tuple(assets)


def _geometry(raw: object) -> GeometrySlot | None | Err:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"kind", "version", "document"}:
        return Err("not_draft", "geometry must be empty or a reserved document")
    if (
        raw["kind"] != GEOMETRY_KIND
        or isinstance(raw["version"], bool)
        or raw["version"] != 1
        or not isinstance(raw["document"], dict)
    ):
        return Err("not_draft", "geometry must be empty or a reserved document")
    return GeometrySlot(1, _json_object(raw["document"]))


def _json_object(document: dict) -> str:
    import json

    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
