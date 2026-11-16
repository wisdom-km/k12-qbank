"""Plain page face copied onto a PDF. No name field. No I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperPage:
    """What a synthetic page may show. student_id is the number, not a name."""

    question_version_id: str
    answer_version_id: str
    formula: str
    answer_text: str
    student_id: str
    page_number: int
    item_order: tuple[str, ...]
    asset_ids: tuple[str, ...]
    layout_template_id: str


def formula_from_stem(stem: str) -> str:
    """The math after the label colon. The full stem stays on the question record."""
    text = stem.strip()
    for separator in ("：", ":"):
        if separator in text:
            text = text.split(separator, 1)[1].strip()
            break
    return text
