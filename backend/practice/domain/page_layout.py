"""Fixed answer box and corner marks.

Slot coordinates are a function of (slots_per_page, slot_no, slot_span) only.
slots_per_page 1 is the old one-item page. slots_per_page 4 is the trial face.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from backend.practice.domain.formula import (
    FormulaFault,
    layout_question,
    needs_structure,
    option_rows,
    place_lines,
    row_extent,
)
from backend.practice.domain.item import PracticeItem

BOX_X = 72
BOX_Y = 220
BOX_W = 451
BOX_H = 220
MARK = 18
_PAGE_W = 595
_PAGE_H = 842

SLOTS_PER_PAGE = 4
CONTENT_TOP = 700
CONTENT_BOTTOM = 48
SLOT_H = (CONTENT_TOP - CONTENT_BOTTOM) // SLOTS_PER_PAGE
TEXT_X = 48
TEXT_WIDTH = 480
LINE_H = 16
SLOT_BOX_H = 72
SLOT_BOX_GAP = 6
SLOT_FONT = 12


def answer_box(order_no: int) -> tuple[int, int, int, int]:
    """Return x, y, width, height in PDF points. order_no selects the page.

    This rectangle is the slots_per_page 1 box. A 4-slot page uses slot_answer_box.
    """
    if order_no < 1:
        raise ValueError("order_no")
    return (BOX_X, BOX_Y, BOX_W, BOX_H)


def slot_answer_box(slots_per_page: int, slot_no: int, slot_span: int) -> tuple[int, int, int, int]:
    """Return x, y, width, height. The same inputs always return the same box."""
    if slot_no < 1 or slot_span < 1:
        raise ValueError("slot")
    if slots_per_page == 1:
        return answer_box(1)
    if slots_per_page != SLOTS_PER_PAGE:
        raise ValueError("slots_per_page")
    if slot_no + slot_span - 1 > SLOTS_PER_PAGE:
        raise ValueError("slot")
    top = CONTENT_TOP - (slot_no - 1) * SLOT_H
    bottom = top - slot_span * SLOT_H
    return (BOX_X, bottom + SLOT_BOX_GAP, BOX_W, SLOT_BOX_H)


def alignment_marks() -> tuple[tuple[int, int, int, int], ...]:
    """Four filled squares, one in each corner. The same on every page."""
    inset = 18
    return (
        (inset, inset, MARK, MARK),
        (_PAGE_W - inset - MARK, inset, MARK, MARK),
        (inset, _PAGE_H - inset - MARK, MARK, MARK),
        (_PAGE_W - inset - MARK, _PAGE_H - inset - MARK, MARK, MARK),
    )


def qr_origin() -> tuple[int, int, int]:
    """Left, bottom, and module size of the code, in PDF points."""
    module = 3
    quiet = 18 + MARK + 8
    return (_PAGE_W - quiet - 29 * module, _PAGE_H - quiet - 29 * module, module)


def line_capacity(slot_span: int) -> int:
    """How many text lines fit above the answer box of a span this tall."""
    if slot_span < 1:
        raise ValueError("slot_span")
    top = CONTENT_TOP
    bottom = top - slot_span * SLOT_H
    first = top - LINE_H
    floor = bottom + SLOT_BOX_GAP + SLOT_BOX_H + 4
    if first < floor:
        return 1
    return 1 + (first - floor) // LINE_H


def pack_items(items: Sequence[PracticeItem], slots_per_page: int) -> tuple[PracticeItem, ...]:
    """Assign page_no, slot_no, and slot_span. slots_per_page 1 is left as stored."""
    if slots_per_page == 1:
        return tuple(items)
    if slots_per_page != SLOTS_PER_PAGE:
        raise ValueError("slots_per_page")
    page = 1
    cursor = 1
    packed: list[PracticeItem] = []
    for item in items:
        span = _span_for(item)
        if cursor + span - 1 > SLOTS_PER_PAGE:
            page += 1
            cursor = 1
        placed = replace(item, page_no=page, slot_no=cursor, slot_span=span)
        if item.stem_parts is not None:
            placed = _with_slot_draw(placed)
        packed.append(placed)
        cursor += span
        if cursor > SLOTS_PER_PAGE:
            page += 1
            cursor = 1
    return tuple(packed)


def placed_slot_lines(
    order_no: int,
    slot_no: int,
    slot_span: int,
    stem: str,
    options: Sequence[str],
) -> tuple[tuple[str, int, int], ...]:
    """Text lines for one slot, in PDF points. Lines that pass the box are dropped."""
    top = CONTENT_TOP - (slot_no - 1) * SLOT_H
    y = top - LINE_H
    _x, box_y, _w, box_h = slot_answer_box(SLOTS_PER_PAGE, slot_no, slot_span)
    floor = box_y + box_h + 4
    rows: list[tuple[str, int, int]] = []
    for line in item_text_lines(order_no, stem, options):
        if y < floor:
            break
        rows.append((line, TEXT_X, y))
        y -= LINE_H
    return tuple(rows)


def item_text_lines(order_no: int, stem: str, options: Sequence[str]) -> tuple[str, ...]:
    """Question number, stem, and every option. Wrapping uses a fixed width."""
    lines = list(_wrap(f"{order_no}. {stem}"))
    for option in options:
        if option:
            lines.extend(_wrap(option))
    return tuple(lines)


def draw_legacy_formula(item: PracticeItem) -> PracticeItem:
    """One-item pages keep the header and draw the formula below it.

    A plain item is returned unchanged. A command in that plain text is not
    drawn here; the caller refuses formula_unstructured before this runs.
    """
    if item.stem_parts is None:
        return item
    if needs_structure(item.stem_parts, item.stem_text, item.option_parts, item.option_text):
        raise FormulaFault("formula_unstructured", "", item.question_version_id)
    lines = _formula_lines(item, TEXT_WIDTH, TEXT_WIDTH)
    ops, _height = place_lines(lines, TEXT_X, CONTENT_TOP, LINE_H)
    return replace(item, formula_draw=ops, placed_lines=())


def _span_for(item: PracticeItem) -> int:
    if item.stem_parts is not None:
        return _formula_span(item)
    options = tuple(line for line in item.option_text.split("\n") if line)
    count = len(item_text_lines(item.order_no, item.stem_text, options))
    for span in range(1, SLOTS_PER_PAGE + 1):
        if count <= line_capacity(span):
            return span
    return SLOTS_PER_PAGE


def _formula_span(item: PracticeItem) -> int:
    if needs_structure(item.stem_parts, item.stem_text, item.option_parts, item.option_text):
        raise FormulaFault("formula_unstructured", "", item.question_version_id)
    lines = _formula_lines(item, TEXT_WIDTH, TEXT_WIDTH)
    height = 0.0
    for line in lines:
        height += row_extent(line, LINE_H, 0.0)
    for span in range(1, SLOTS_PER_PAGE + 1):
        if height <= line_capacity(span) * LINE_H:
            return span
    return SLOTS_PER_PAGE


def _with_slot_draw(item: PracticeItem) -> PracticeItem:
    top = CONTENT_TOP - (item.slot_no - 1) * SLOT_H
    lines = _formula_lines(item, TEXT_WIDTH, TEXT_WIDTH)
    ops, _height = place_lines(lines, TEXT_X, top, LINE_H)
    return replace(item, formula_draw=ops, placed_lines=())


def _formula_lines(item: PracticeItem, first_width: float, width: float) -> tuple[object, ...]:
    try:
        return layout_question(
            f"{item.order_no}. ",
            item.stem_parts or (),
            option_rows(item.option_parts, tuple(line for line in item.option_text.split("\n") if line)),
            size=SLOT_FONT,
            first_width=first_width,
            width=width,
        )
    except FormulaFault as fault:
        raise FormulaFault(fault.code, fault.command, item.question_version_id) from None


def _wrap(text: str) -> tuple[str, ...]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    if cleaned.strip("\n") == "":
        return ("",)
    lines: list[str] = []
    for paragraph in cleaned.split("\n"):
        if paragraph == "":
            continue
        current: list[str] = []
        used = 0
        for char in paragraph:
            width = 12 if ord(char) > 0x2E80 else 6
            if current and used + width > TEXT_WIDTH:
                lines.append("".join(current))
                current = [char]
                used = width
            else:
                current.append(char)
                used += width
        if current:
            lines.append("".join(current))
    return tuple(lines) or ("",)
