"""Answer-draft contract shared with the review tool. Not a publication.

One file is one answer. A page block list is refused. Nothing here opens a
database or assigns answer_version_id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.kernel.result import Err, Ok

CONTRACT = "k12-answer-draft"
CONTRACT_VERSION = 1
ORIGINS = {"ocr", "model", "teacher"}
STATUSES = {"candidate", "needs_confirm", "confirmed", "disputed"}
FILE_KEYS = {
    "contract",
    "contract_version",
    "ok",
    "reason",
    "question_key",
    "key",
    "origin",
    "status",
    "applicable",
    "source",
    "content",
    "parts",
    "assets",
}
PART_KEYS = {"sub_key", "role", "order", "content"}
_ORDINAL = re.compile(r"^[1-9][0-9]*$")


@dataclass(frozen=True)
class TextPart:
    value: str


@dataclass(frozen=True)
class MathPart:
    latex: str


@dataclass(frozen=True)
class AnswerPart:
    sub_key: str
    role: str
    order: int
    content: tuple[TextPart | MathPart, ...]


@dataclass(frozen=True)
class AnswerAsset:
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class AnswerDraft:
    question_key: str
    key: str
    origin: str
    status: str
    applicable: bool
    pdf_page: int | None
    model_task_id: str | None
    content: tuple[TextPart | MathPart, ...]
    parts: tuple[AnswerPart, ...]
    assets: tuple[AnswerAsset, ...]
    ok: bool
    reason: str


def parse_answer_draft(payload: object) -> Ok[AnswerDraft] | Err:
    """Accept one answer file. A page block list is refused."""
    if isinstance(payload, list):
        return Err("not_draft", "a page block list is not an answer draft")
    if not isinstance(payload, dict):
        return Err("not_draft", "an answer draft must be an object")
    if set(payload) != FILE_KEYS:
        return Err("not_draft", "the answer file keys do not match version 1")
    version = payload["contract_version"]
    if payload["contract"] != CONTRACT or isinstance(version, bool) or version != CONTRACT_VERSION:
        return Err("not_draft", "the answer contract is not version 1")
    if not isinstance(payload["ok"], bool) or not isinstance(payload["reason"], str):
        return Err("not_draft", "ok and reason have the wrong shape")
    if payload["origin"] not in ORIGINS or payload["status"] not in STATUSES:
        return Err("not_draft", "the answer origin or status is unknown")
    if not isinstance(payload["applicable"], bool):
        return Err("not_draft", "applicable must be true or false")
    if payload["origin"] == "model" and payload["applicable"]:
        return Err("not_draft", "a model answer cannot be applicable")
    if payload["applicable"] and payload["status"] != "confirmed":
        return Err("not_draft", "an applicable answer must be confirmed")
    if payload["applicable"] and not payload["ok"]:
        return Err("not_draft", "a refused answer cannot be applicable")
    if not isinstance(payload["question_key"], str) or not payload["question_key"].strip():
        return Err("not_draft", "question_key must be text")
    if not isinstance(payload["key"], str) or not _key_matches(
        payload["question_key"], payload["origin"], payload["key"]
    ):
        return Err("not_draft", "the answer key must be question, origin, and ordinal")
    source = _source(payload["origin"], payload["source"])
    if isinstance(source, Err):
        return source
    pdf_page, model_task_id = source
    content = _parts(payload["content"])
    if isinstance(content, Err):
        return content
    parts = _answer_parts(payload["parts"])
    if isinstance(parts, Err):
        return parts
    assets = _assets(payload["assets"])
    if isinstance(assets, Err):
        return assets
    return Ok(
        AnswerDraft(
            question_key=payload["question_key"],
            key=payload["key"],
            origin=payload["origin"],
            status=payload["status"],
            applicable=payload["applicable"],
            pdf_page=pdf_page,
            model_task_id=model_task_id,
            content=content,
            parts=parts,
            assets=assets,
            ok=payload["ok"],
            reason=payload["reason"],
        )
    )


def answer_not_publication(draft: AnswerDraft) -> Err:
    """A draft never becomes a publication, even when a teacher adopts the scan."""
    if not draft.key.strip():
        return Err("not_draft", "an answer draft needs a key")
    return Err("draft", "an answer draft is not a publication")


def _key_matches(question_key: str, origin: str, key: str) -> bool:
    prefix = f"{question_key}:{origin}:"
    if not key.startswith(prefix):
        return False
    return _ORDINAL.match(key[len(prefix) :]) is not None


def _source(origin: str, source: object) -> tuple[int | None, str | None] | Err:
    if not isinstance(source, dict):
        return Err("not_draft", "source has the wrong shape")
    if origin == "ocr":
        if set(source) != {"pdf_page"}:
            return Err("not_draft", "an ocr answer source names only a pdf page")
        page = source["pdf_page"]
        if page is None:
            return None, None
        if isinstance(page, bool) or not isinstance(page, int):
            return Err("not_draft", "pdf_page must be a whole number or empty")
        return page, None
    if origin == "model":
        if set(source) != {"model_task_id"}:
            return Err("not_draft", "a model answer source names only a task id")
        task_id = source["model_task_id"]
        if not isinstance(task_id, str) or not task_id.strip() or "\n" in task_id:
            return Err("not_draft", "model_task_id must be a single line")
        return None, task_id
    if set(source) != set():
        return Err("not_draft", "a teacher answer source is empty")
    return None, None


def _parts(raw: object) -> tuple[TextPart | MathPart, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "answer content must be a list")
    parts: list[TextPart | MathPart] = []
    for part in raw:
        if not isinstance(part, dict):
            return Err("not_draft", "an answer part must be an object")
        if set(part) == {"type", "value"} and part["type"] == "text" and isinstance(part["value"], str):
            parts.append(TextPart(part["value"]))
            continue
        if set(part) == {"type", "latex"} and part["type"] == "math" and isinstance(part["latex"], str):
            parts.append(MathPart(part["latex"]))
            continue
        return Err("not_draft", "an answer fragment must be text or math")
    return tuple(parts)


def _answer_parts(raw: object) -> tuple[AnswerPart, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "parts must be a list")
    parsed: list[AnswerPart] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != PART_KEYS:
            return Err("not_draft", "an answer part has the wrong fields")
        if item["role"] not in {"result", "step"}:
            return Err("not_draft", "an answer part role must be result or step")
        order = item["order"]
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            return Err("not_draft", "an answer part order must be a positive whole number")
        if not isinstance(item["sub_key"], str):
            return Err("not_draft", "sub_key must be text")
        content = _parts(item["content"])
        if isinstance(content, Err):
            return content
        if not content:
            return Err("not_draft", "an answer part needs content")
        parsed.append(AnswerPart(item["sub_key"], item["role"], order, content))
    return tuple(parsed)


def _assets(raw: object) -> tuple[AnswerAsset, ...] | Err:
    if not isinstance(raw, list):
        return Err("not_draft", "assets must be a list")
    assets: list[AnswerAsset] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"role", "bbox"} or item["role"] != "crop":
            return Err("not_draft", "an answer asset must be a crop")
        bbox = item["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4 or any(not _number(value) for value in bbox):
            return Err("not_draft", "a crop needs four coordinates")
        assets.append(AnswerAsset(tuple(float(value) for value in bbox)))
    return tuple(assets)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
