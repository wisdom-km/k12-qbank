"""Plain page face copied onto a PDF. No name field. No answer. No I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotFace:
    """One question drawn in a fixed slot. The box comes from slot_answer_box."""

    order_no: int
    slot_no: int
    slot_span: int
    stem: str
    options: tuple[str, ...]
    answer_box: tuple[int, int, int, int]
    drawn: bool = False


@dataclass(frozen=True)
class PaperPage:
    """What a synthetic student page may show.

    student_id is the number, not a name. The answer and the explanation stay
    off this face. paper_id distinguishes two papers for the same student.
    """

    question_version_id: str
    answer_version_id: str
    formula: str
    student_id: str
    page_number: int
    item_order: tuple[str, ...]
    asset_ids: tuple[str, ...]
    layout_template_id: str
    paper_id: str
    page_count: int
    printed_external_id: str = ""
    qr_printed: bool = False
    stem: str = ""
    slots: tuple[SlotFace, ...] = ()
    flow: bool = False
    flow_lines: tuple[tuple[str, float, float, float], ...] = ()
    flow_boxes: tuple[tuple[float, float, float, float], ...] = ()
    flow_marks: tuple[tuple[float, float, float, float], ...] = ()
    flow_qr: tuple[float, float, float] | None = None
    extra_runs: tuple[tuple[object, ...], ...] = ()
    draw_rules: tuple[tuple[float, float, float, float], ...] = ()


def formula_from_stem(stem: str) -> str:
    """The math after the label colon. The full stem stays on the question record."""
    text = stem.strip()
    for separator in ("：", ":"):
        if separator in text:
            text = text.split(separator, 1)[1].strip()
            break
    return text
