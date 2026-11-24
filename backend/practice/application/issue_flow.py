"""Turn approved questions into a flow placement. Stores nothing."""

from __future__ import annotations

from dataclasses import replace

from backend.catalog.api import ApprovalSnapshot, resolved_space
from backend.kernel.result import Err
from backend.practice.domain.flow_layout import (
    FlowQuestion,
    ItemTooLong,
    PlacedItem,
    blank_count,
    dump_layout,
    flow_place,
)
from backend.practice.domain.item import ItemBox, PracticeItem
from backend.practice.domain.layout_params import LayoutError, load_layout


def place_flow(
    items: tuple[PracticeItem, ...],
    snapshots: tuple[ApprovalSnapshot, ...],
) -> tuple[tuple[PracticeItem, ...], str] | Err:
    """Place items. The JSON is the chrome stored on the paper."""
    loaded = load_layout()
    if isinstance(loaded, LayoutError):
        return Err("layout_invalid", loaded.message)
    questions: list[FlowQuestion] = []
    for item, snapshot in zip(items, snapshots, strict=True):
        space, _default = resolved_space(snapshot.answer_space, snapshot.type)
        count = blank_count(item.stem_text) if space == "blanks" else 1
        questions.append(
            FlowQuestion(
                order_no=item.order_no,
                question_version_id=item.question_version_id,
                stem=item.stem_text,
                options=tuple(line for line in item.option_text.split("\n") if line),
                space=space,
                blank_count=count,
            )
        )
    placed = flow_place(tuple(questions), loaded)
    if isinstance(placed, ItemTooLong):
        return Err(
            "item_too_long",
            f"第 {placed.order_no} 题放不下一整页（{placed.question_version_id}）",
        )
    by_order = {item.order_no: item for item in placed}
    stored = tuple(_copy(item, by_order[item.order_no]) for item in items)
    return stored, dump_layout(loaded)


def _copy(item: PracticeItem, placed: PlacedItem) -> PracticeItem:
    return replace(
        item,
        page_no=placed.page_no,
        placed_lines=tuple((line.text, line.x, line.y) for line in placed.lines),
        boxes=tuple(
            ItemBox(box.box_no, box.page_no, box.x, box.y, box.w, box.h, box.kind) for box in placed.boxes
        ),
    )
