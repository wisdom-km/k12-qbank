"""Paper layout parameters. Production refuses an illegal file at startup."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_MIN = {
    "qr_module": 1.7,
    "qr_quiet_modules": 4,
    "mark_size": 12,
    "header_font_size": 9,
    "letter_width": 28,
    "letter_height": 20,
}
_INT_FIELDS = {"qr_quiet_modules"}
_FIELDS = (
    "page_width",
    "page_height",
    "margin_left",
    "margin_right",
    "margin_top",
    "margin_bottom",
    "font_size",
    "line_height",
    "header_x",
    "header_y",
    "header_font_size",
    "qr_module",
    "qr_quiet_modules",
    "mark_size",
    "mark_inset",
    "letter_width",
    "letter_height",
    "blank_width",
    "blank_height",
    "blank_gap",
    "small_height",
    "medium_height",
    "large_height",
    "item_gap",
)


@dataclass(frozen=True)
class LayoutParams:
    page_width: float
    page_height: float
    margin_left: float
    margin_right: float
    margin_top: float
    margin_bottom: float
    font_size: float
    line_height: float
    header_x: float
    header_y: float
    header_font_size: float
    qr_module: float
    qr_quiet_modules: int
    mark_size: float
    mark_inset: float
    letter_width: float
    letter_height: float
    blank_width: float
    blank_height: float
    blank_gap: float
    small_height: float
    medium_height: float
    large_height: float
    item_gap: float


@dataclass(frozen=True)
class LayoutError:
    field: str
    message: str


def bundled_layout_path() -> Path:
    return Path(__file__).with_name("paper_layout.json")


def layout_path() -> Path:
    raw = os.environ.get("K12_PAPER_LAYOUT_PATH", "").strip()
    if raw:
        return Path(raw)
    return bundled_layout_path()


def load_layout(path: Path | None = None) -> LayoutParams | LayoutError:
    """Read one JSON file. The message names the field that failed."""
    source = layout_path() if path is None else path
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LayoutError("file", "版式参数文件无法读取")
    if not isinstance(raw, dict):
        return LayoutError("file", "版式参数文件必须是对象")
    extra = set(raw) - set(_FIELDS)
    if extra:
        name = sorted(extra)[0]
        return LayoutError(name, name + " 不能识别")
    values: dict[str, float] = {}
    for name in _FIELDS:
        if name not in raw:
            return LayoutError(name, name + " 缺少")
        parsed = _number(name, raw[name])
        if isinstance(parsed, LayoutError):
            return parsed
        floor = _MIN.get(name)
        if floor is not None and parsed < floor:
            return LayoutError(name, name + " 小于下限 " + _text(floor))
        if name not in _MIN and parsed < 0:
            return LayoutError(name, name + " 小于下限 0")
        values[name] = parsed
    if values["line_height"] < values["font_size"]:
        return LayoutError("line_height", "line_height 小于下限 " + _text(values["font_size"]))
    params = LayoutParams(
        page_width=values["page_width"],
        page_height=values["page_height"],
        margin_left=values["margin_left"],
        margin_right=values["margin_right"],
        margin_top=values["margin_top"],
        margin_bottom=values["margin_bottom"],
        font_size=values["font_size"],
        line_height=values["line_height"],
        header_x=values["header_x"],
        header_y=values["header_y"],
        header_font_size=values["header_font_size"],
        qr_module=values["qr_module"],
        qr_quiet_modules=int(values["qr_quiet_modules"]),
        mark_size=values["mark_size"],
        mark_inset=values["mark_inset"],
        letter_width=values["letter_width"],
        letter_height=values["letter_height"],
        blank_width=values["blank_width"],
        blank_height=values["blank_height"],
        blank_gap=values["blank_gap"],
        small_height=values["small_height"],
        medium_height=values["medium_height"],
        large_height=values["large_height"],
        item_gap=values["item_gap"],
    )
    return params


def _number(name: str, value: object) -> float | LayoutError:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return LayoutError(name, name + " 不是数字")
    if name in _INT_FIELDS and not isinstance(value, int):
        return LayoutError(name, name + " 不是整数")
    return float(value)


def _text(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)
