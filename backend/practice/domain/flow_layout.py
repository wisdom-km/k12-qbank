"""Flow layout. The same questions and parameters always return the same boxes.

Letter boxes sit on the question-number line. Blank boxes sit under the stem.
A full box uses the content height still free on the page. A question that
cannot fit on an empty page is item_too_long. No line is dropped.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from backend.practice.domain.formula import (
    FormulaFault,
    LineBox,
    fault_message,
    layout_question,
    needs_structure,
    option_rows,
    place_lines,
    row_extent,
)
from backend.practice.domain.layout_params import LayoutParams

_BLANKS = re.compile(r"_{2,}")
_QR_MODULES = 29


@dataclass(frozen=True)
class FlowQuestion:
    order_no: int
    question_version_id: str
    stem: str
    options: tuple[str, ...]
    space: str
    blank_count: int
    stem_parts: tuple[tuple[str, str], ...] | None = None
    option_parts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None = None


@dataclass(frozen=True)
class PlacedLine:
    text: str
    x: float
    y: float


@dataclass(frozen=True)
class PlacedBox:
    order_no: int
    box_no: int
    page_no: int
    x: float
    y: float
    w: float
    h: float
    kind: str


@dataclass(frozen=True)
class PlacedItem:
    order_no: int
    question_version_id: str
    page_no: int
    lines: tuple[PlacedLine, ...]
    boxes: tuple[PlacedBox, ...]
    draw: tuple[tuple[object, ...], ...] | None = None


@dataclass(frozen=True)
class ItemTooLong:
    order_no: int
    question_version_id: str


@dataclass(frozen=True)
class FormulaStop:
    """The paper is refused. code is one of the formula_* outcomes."""

    order_no: int
    question_version_id: str
    code: str
    command: str = ""


def blank_count(stem: str) -> int:
    """Count underscore blanks. A fill-in stem with none still gets one box."""
    found = len(_BLANKS.findall(stem))
    return found if found else 1


def header_text(external_id: str, page_no: int, page_count: int) -> str:
    """Student number plus the page label. No name, class, or internal id."""
    label = f"第 {page_no} 页 / 共 {page_count} 页"
    if external_id:
        return external_id + "  " + label
    return label


def chrome_of(params: LayoutParams) -> dict[str, object]:
    """Header, marks, and QR origin. Stored on the paper at issue time."""
    code = _QR_MODULES * params.qr_module
    quiet = params.qr_quiet_modules * params.qr_module
    inset = params.mark_inset
    size = params.mark_size
    width = params.page_width
    height = params.page_height
    marks = (
        (inset, inset, size, size),
        (width - inset - size, inset, size, size),
        (inset, height - inset - size, size, size),
        (width - inset - size, height - inset - size, size, size),
    )
    return {
        "marks": [list(mark) for mark in marks],
        "qr": {
            "x": width - params.margin_right - quiet - code,
            "y": height - params.margin_top - quiet - code,
            "module": params.qr_module,
        },
        "header": {
            "x": params.header_x,
            "y": params.header_y,
            "font_size": params.header_font_size,
        },
        "body_font_size": params.font_size,
    }


def dump_layout(params: LayoutParams) -> str:
    return json.dumps(chrome_of(params), ensure_ascii=False, separators=(",", ":"))


def flow_place(
    questions: tuple[FlowQuestion, ...], params: LayoutParams
) -> tuple[PlacedItem, ...] | ItemTooLong | FormulaStop:
    """Place every question. A too-long item returns before any page is kept."""
    area = _content(params)
    if area.top - area.bottom <= 0:
        first = questions[0] if questions else FlowQuestion(1, "", "", (), "medium", 1)
        return ItemTooLong(first.order_no, first.question_version_id)
    placed: list[PlacedItem] = []
    page_no = 1
    cursor = area.top
    for question in questions:
        block, stopped = _formula_block(question, params, area)
        if stopped is not None:
            return stopped
        needed = _needed(question, params, area, cursor, block)
        if isinstance(needed, ItemTooLong):
            return needed
        if needed.start == area.top and cursor < area.top:
            page_no += 1
        item = _draw(question, params, area, needed.start, page_no, needed.answer_h, block)
        placed.append(item)
        cursor = needed.start - needed.used
        if question.space == "full":
            page_no += 1
            cursor = area.top
    return tuple(placed)


@dataclass(frozen=True)
class _Need:
    start: float
    answer_h: float
    used: float


def _needed(
    question: FlowQuestion,
    params: LayoutParams,
    area: _Area,
    cursor: float,
    block: tuple[LineBox, ...] | None = None,
) -> _Need | ItemTooLong:
    text_h = _text_height(question, params, area, block)
    page_h = area.top - area.bottom
    if question.space == "full":
        if text_h + params.item_gap >= page_h:
            return ItemTooLong(question.order_no, question.question_version_id)
        start = cursor
        if cursor - area.bottom < text_h + params.item_gap + params.large_height and cursor < area.top:
            start = area.top
        answer_h = (start - area.bottom) - text_h
        if answer_h <= 0:
            return ItemTooLong(question.order_no, question.question_version_id)
        return _Need(start, answer_h, text_h + answer_h)
    answer_h = _answer_height(question, params, area)
    used = text_h + answer_h + params.item_gap
    if used > page_h:
        return ItemTooLong(question.order_no, question.question_version_id)
    start = cursor
    if cursor - area.bottom < used and cursor < area.top:
        start = area.top
    return _Need(start, answer_h, used)


def _draw(
    question: FlowQuestion,
    params: LayoutParams,
    area: _Area,
    top: float,
    page_no: int,
    answer_h: float,
    block: tuple[LineBox, ...] | None = None,
) -> PlacedItem:
    if block is not None:
        return _draw_formula(question, params, area, top, page_no, answer_h, block)
    lines = _lines(question, params, area)
    placed: list[PlacedLine] = []
    boxes: list[PlacedBox] = []
    cursor = top
    for index, line in enumerate(lines):
        row_h = params.line_height
        if index == 0 and question.space == "letter":
            row_h = max(params.line_height, params.letter_height)
        baseline = cursor - row_h + 4
        placed.append(PlacedLine(line, area.left, baseline))
        if index == 0 and question.space == "letter":
            boxes.append(
                PlacedBox(
                    question.order_no,
                    1,
                    page_no,
                    area.right - params.letter_width,
                    cursor - params.letter_height,
                    params.letter_width,
                    params.letter_height,
                    "letter",
                )
            )
        cursor -= row_h
    if question.space == "blanks":
        boxes.extend(_blank_boxes(question, params, area, cursor, page_no))
    elif question.space in {"small", "medium", "large", "full"}:
        boxes.append(
            PlacedBox(
                question.order_no,
                1,
                page_no,
                area.left,
                cursor - answer_h,
                area.right - area.left,
                answer_h,
                question.space,
            )
        )
    return PlacedItem(
        question.order_no,
        question.question_version_id,
        page_no,
        tuple(placed),
        tuple(boxes),
    )


def _blank_boxes(
    question: FlowQuestion,
    params: LayoutParams,
    area: _Area,
    top: float,
    page_no: int,
) -> tuple[PlacedBox, ...]:
    width = area.right - area.left
    slot = params.blank_width + params.blank_gap
    per_row = max(1, int(math.floor((width + params.blank_gap) / slot)))
    boxes: list[PlacedBox] = []
    for index in range(question.blank_count):
        row, col = divmod(index, per_row)
        boxes.append(
            PlacedBox(
                question.order_no,
                index + 1,
                page_no,
                area.left + col * slot,
                top - (row + 1) * params.blank_height - row * params.blank_gap,
                params.blank_width,
                params.blank_height,
                "blanks",
            )
        )
    return tuple(boxes)


def _draw_formula(
    question: FlowQuestion,
    params: LayoutParams,
    area: _Area,
    top: float,
    page_no: int,
    answer_h: float,
    block: tuple[LineBox, ...],
) -> PlacedItem:
    first = params.letter_height if question.space == "letter" else 0.0
    ops, text_h = place_lines(block, area.left, top, params.line_height, first_row=first)
    cursor = top - text_h
    boxes: list[PlacedBox] = []
    if question.space == "letter":
        boxes.append(
            PlacedBox(
                question.order_no,
                1,
                page_no,
                area.right - params.letter_width,
                top - params.letter_height,
                params.letter_width,
                params.letter_height,
                "letter",
            )
        )
    if question.space == "blanks":
        boxes.extend(_blank_boxes(question, params, area, cursor, page_no))
    elif question.space in {"small", "medium", "large", "full"}:
        boxes.append(
            PlacedBox(
                question.order_no,
                1,
                page_no,
                area.left,
                cursor - answer_h,
                area.right - area.left,
                answer_h,
                question.space,
            )
        )
    return PlacedItem(
        question.order_no,
        question.question_version_id,
        page_no,
        (),
        tuple(boxes),
        ops,
    )


def _formula_block(
    question: FlowQuestion, params: LayoutParams, area: _Area
) -> tuple[tuple[LineBox, ...] | None, FormulaStop | None]:
    option_text = "\n".join(question.options)
    if needs_structure(question.stem_parts, question.stem, question.option_parts, option_text):
        return None, FormulaStop(question.order_no, question.question_version_id, "formula_unstructured")
    if question.stem_parts is None:
        return None, None
    width = area.right - area.left
    first = width
    if question.space == "letter":
        first = max(params.font_size, width - params.letter_width - 8)
    try:
        lines = layout_question(
            f"{question.order_no}. ",
            question.stem_parts,
            option_rows(question.option_parts, question.options),
            size=float(params.font_size),
            first_width=first,
            width=width,
        )
    except FormulaFault as fault:
        code, _message = fault_message(question.question_version_id, fault.code, fault.command)
        return None, FormulaStop(question.order_no, question.question_version_id, code, fault.command)
    return lines, None


def _lines(question: FlowQuestion, params: LayoutParams, area: _Area) -> tuple[str, ...]:
    width = area.right - area.left
    first = width
    if question.space == "letter":
        first = max(params.font_size, width - params.letter_width - 8)
    rows = list(_wrap(f"{question.order_no}. {question.stem}", first, width, params.font_size))
    for option in question.options:
        if option:
            rows.extend(_wrap(option, width, width, params.font_size))
    return tuple(rows) or ("",)


def _text_height(
    question: FlowQuestion,
    params: LayoutParams,
    area: _Area,
    block: tuple[LineBox, ...] | None = None,
) -> float:
    if block is not None:
        first = params.letter_height if question.space == "letter" else 0.0
        height = 0.0
        for index, line in enumerate(block):
            height += row_extent(line, params.line_height, first if index == 0 else 0.0)
        return height
    lines = _lines(question, params, area)
    height = 0.0
    for index in range(len(lines)):
        row = params.line_height
        if index == 0 and question.space == "letter":
            row = max(params.line_height, params.letter_height)
        height += row
    return height


def _answer_height(question: FlowQuestion, params: LayoutParams, area: _Area) -> float:
    if question.space == "letter":
        return 0.0
    if question.space == "blanks":
        width = area.right - area.left
        slot = params.blank_width + params.blank_gap
        per_row = max(1, int(math.floor((width + params.blank_gap) / slot)))
        rows = math.ceil(question.blank_count / per_row)
        return rows * params.blank_height + (rows - 1) * params.blank_gap
    if question.space == "small":
        return params.small_height
    if question.space == "medium":
        return params.medium_height
    return params.large_height


@dataclass(frozen=True)
class _Area:
    left: float
    right: float
    top: float
    bottom: float


def _content(params: LayoutParams) -> _Area:
    code = _QR_MODULES * params.qr_module
    quiet = params.qr_quiet_modules * params.qr_module
    qr_bottom = params.page_height - params.margin_top - quiet - code
    header_clear = params.header_y - params.header_font_size - 6
    top = min(qr_bottom - 8, header_clear)
    return _Area(
        left=params.margin_left,
        right=params.page_width - params.margin_right,
        top=top,
        bottom=params.margin_bottom,
    )


def _wrap(text: str, first_width: float, width: float, font_size: float) -> tuple[str, ...]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    if cleaned.strip("\n") == "":
        return ("",)
    lines: list[str] = []
    limit = first_width
    for paragraph in cleaned.split("\n"):
        if paragraph == "":
            continue
        current: list[str] = []
        used = 0.0
        for char in paragraph:
            char_width = font_size if ord(char) > 0x2E80 else font_size / 2
            if current and used + char_width > limit:
                lines.append("".join(current))
                current = [char]
                used = char_width
                limit = width
            else:
                current.append(char)
                used += char_width
        if current:
            lines.append("".join(current))
            limit = width
    return tuple(lines) or ("",)
