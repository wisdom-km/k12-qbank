"""Local comparison for choices and for blanks that are only digits or letters."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_BLANKS = re.compile(r"_{2,}")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_LETTERS = re.compile(r"^[A-Za-z]+$")
_CHOICE_TYPES = frozenset({"single_choice", "multiple_choice"})
_KNOWN_TYPES = _CHOICE_TYPES | frozenset({"fill_blank", "solution", "composite"})


@dataclass(frozen=True)
class LocalCall:
    verdict: str
    reason: str


def question_type(snapshot_type: str, option_text: str, stem: str, box_kinds: tuple[str, ...]) -> str:
    kind = snapshot_type.strip()
    if kind in _KNOWN_TYPES:
        return kind
    if option_text.strip():
        return "single_choice"
    if "blanks" in box_kinds or _BLANKS.search(stem):
        return "fill_blank"
    return "solution"


def blank_count_of(stem: str) -> int:
    found = _BLANKS.findall(stem)
    return len(found) if found else 1


def grade_local(
    kind: str,
    standard: str,
    transcription: str,
    unreadable: bool,
    blank_count: int,
) -> LocalCall | None:
    """Return a local verdict, or None when this item must go to the model."""
    if unreadable:
        return LocalCall("unsure", "看不清")
    if kind in _CHOICE_TYPES:
        same = normalize_choice(transcription) == normalize_choice(standard)
        if same:
            return LocalCall("correct", "与标准答案一致")
        return LocalCall("incorrect", "与标准答案不一致")
    if kind != "fill_blank":
        return None
    count = blank_count if blank_count > 0 else 1
    student = _split(transcription, count)
    expected = _split(standard, count)
    if student is None or expected is None:
        return None
    if any(not _pure(part) for part in student + expected):
        return None
    matches = [left == right for left, right in zip(student, expected)]
    if all(matches):
        return LocalCall("correct", "与标准答案一致")
    if any(matches):
        return LocalCall("partial", "部分空与标准答案一致")
    return LocalCall("incorrect", "与标准答案不一致")


def normalize_choice(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(folded.split())
    for mark in (",", "，", "、", ";", "；"):
        folded = folded.replace(mark, "")
    folded = folded.upper()
    if folded and all("A" <= char <= "Z" for char in folded):
        return "".join(sorted(folded))
    return folded


def _split(text: str, count: int) -> list[str] | None:
    if count <= 1:
        return [_normalize_blank(text)]
    raw = unicodedata.normalize("NFKC", text)
    chunks = [part.strip() for part in re.split(r"[\n;；]+", raw) if part.strip()]
    if len(chunks) != count:
        return None
    return [_normalize_blank(part) for part in chunks]


def _normalize_blank(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).replace("\u2212", "-")
    folded = "".join(folded.split())
    if _LETTERS.fullmatch(folded):
        return folded.upper()
    return folded


def _pure(text: str) -> bool:
    return _NUMBER.fullmatch(text) is not None or _LETTERS.fullmatch(text) is not None
