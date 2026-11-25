"""Lay out one formula. The function is pure: no font file, no I/O.

Glyph y is the baseline relative to the formula baseline. Positive y is up.
A command this module does not know raises FormulaFault. It does not invent
a reading of the source, and it does not return the source as a glyph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCRIPT_SCALE = 0.7
SUPERSCRIPT_RISE = 0.45
SUBSCRIPT_DROP = 0.22
FRACTION_GAP = 0.16
FRACTION_AXIS = 0.22

_COMMAND = re.compile(r"\\(?:[A-Za-z]+|.)")
_OPERATORS = set("+-*=<>")
_SYMBOLS = {
    "times": "×",
    "div": "÷",
    "pm": "±",
    "cdot": "·",
    "neq": "≠",
    "approx": "≈",
    "leq": "≤",
    "geq": "≥",
    "le": "≤",
    "ge": "≥",
    "angle": "∠",
    "circ": "°",
    "prime": "′",
    "pi": "π",
}
_SPACES = {",": 0.17, ";": 0.28, "quad": 1.0, " ": 0.33, "~": 0.33}
_KNOWN = set(_SYMBOLS) | set(_SPACES) | {
    "frac",
    "dfrac",
    "tfrac",
    "left",
    "right",
    "text",
    "textcircled",
    "mathrm",
    "%",
    "{",
    "}",
    "|",
}


class FormulaFault(Exception):
    """code is formula_unsupported or formula_too_wide. command is empty or '\\name'."""

    def __init__(self, code: str, command: str = "", question_version_id: str = "") -> None:
        self.code = code
        self.command = command
        self.question_version_id = question_version_id
        super().__init__(code)


@dataclass(frozen=True)
class Glyph:
    text: str
    x: float
    y: float
    size: float
    font: str
    scale_y: float = 1.0


@dataclass(frozen=True)
class Rule:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class FormulaBox:
    glyphs: tuple[Glyph, ...]
    rules: tuple[Rule, ...]
    width: float
    ascent: float
    descent: float

    @property
    def height(self) -> float:
        return self.ascent + self.descent

    @property
    def baseline(self) -> float:
        """Distance from the bottom of the box to the baseline."""
        return self.descent


@dataclass(frozen=True)
class LineBox:
    """One wrapped row. Glyph y is relative to this row's baseline."""

    glyphs: tuple[Glyph, ...]
    rules: tuple[Rule, ...]
    ascent: float
    descent: float


def plain_has_command(text: str) -> bool:
    """True when the plain stem still contains a backslash command.

    This does not decide where a formula starts. It only refuses to print
    source that was never split into parts.
    """
    return _COMMAND.search(text) is not None


def unsupported_commands(latex: str) -> tuple[str, ...]:
    """Command names this layout will not draw, in source order, without duplicates."""
    found: list[str] = []
    for match in _COMMAND.finditer(latex):
        name = match.group(0)[1:]
        if name not in _KNOWN and match.group(0) not in found:
            found.append(match.group(0))
    return tuple(found)


def layout_math(latex: str, size: float) -> FormulaBox:
    """Lay out one math fragment at this font size."""
    if size <= 0:
        raise FormulaFault("formula_unsupported", "")
    nodes = _parse(latex)
    return _hbox(nodes, size)


def layout_question(
    prefix: str,
    parts: tuple[tuple[str, str], ...],
    options: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
    *,
    size: float,
    first_width: float,
    width: float,
) -> tuple[LineBox, ...]:
    """Wrap text and keep each formula on one line. A wide formula is formula_too_wide."""
    rows = _wrap_pieces(_pieces(prefix, parts), size, first_width, width)
    for key, content in options:
        rows.extend(_wrap_pieces(_pieces(f"{key}. ", content), size, width, width))
    return tuple(rows) or (LineBox((), (), size * 0.8, size * 0.2),)


def place_lines(
    lines: tuple[LineBox, ...],
    left: float,
    top: float,
    line_height: float,
    *,
    first_row: float = 0,
) -> tuple[tuple[tuple[object, ...], ...], float]:
    """Return draw ops and the height consumed. y grows upward, top is the row top."""
    ops: list[tuple[object, ...]] = []
    cursor = top
    for index, line in enumerate(lines):
        row = row_extent(line, line_height, first_row if index == 0 else 0.0)
        baseline = cursor - row + line.descent
        for glyph in line.glyphs:
            ops.append(("g", glyph.text, left + glyph.x, baseline + glyph.y, glyph.size, glyph.font, glyph.scale_y))
        for rule in line.rules:
            ops.append(("r", left + rule.x1, baseline + rule.y1, left + rule.x2, baseline + rule.y2))
        cursor -= row
    return tuple(ops), top - cursor


def row_extent(line: LineBox, line_height: float, first_row: float) -> float:
    """One row is at least the body line height, and at least the formula's own height."""
    row = max(line_height, line.ascent + line.descent)
    if first_row > row:
        return first_row
    return row


def fault_message(question_version_id: str, code: str, command: str = "") -> tuple[str, str]:
    """HTTP code and the sentence that names the question. The sentence has no source."""
    if code == "formula_too_wide":
        return "formula_too_wide", f"{question_version_id} 公式比一行宽"
    if code == "formula_unstructured":
        return "formula_unstructured", f"{question_version_id} 公式未结构化"
    return "formula_unsupported", f"{question_version_id} 不支持命令 {command}"


def needs_structure(
    stem_parts: tuple[tuple[str, str], ...] | None,
    stem_text: str,
    option_parts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None,
    option_text: str,
) -> bool:
    """True when plain text still holds a command and no part list was stored."""
    if stem_parts is None:
        return plain_has_command(stem_text) or plain_has_command(option_text)
    if option_parts is None and plain_has_command(option_text):
        return True
    return False


def option_rows(
    option_parts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None,
    option_lines: tuple[str, ...],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Use stored option parts. Plain lines stay text and are not scanned for commands."""
    if option_parts is not None:
        return option_parts
    rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for line in option_lines:
        if not line:
            continue
        key, dot, rest = line.partition(". ")
        if dot:
            rows.append((key, (("text", rest),)))
        else:
            rows.append(("", (("text", line),)))
    return tuple(rows)


def split_draw(
    ops: tuple[tuple[object, ...], ...] | None,
) -> tuple[tuple[tuple[object, ...], ...], tuple[tuple[float, float, float, float], ...]]:
    """Separate glyph runs from rules. None and an empty tuple both draw nothing."""
    if not ops:
        return (), ()
    runs: list[tuple[object, ...]] = []
    rules: list[tuple[float, float, float, float]] = []
    for op in ops:
        if op[0] == "g":
            runs.append((op[1], float(op[2]), float(op[3]), float(op[4]), str(op[5]), float(op[6])))
        elif op[0] == "r":
            rules.append((float(op[1]), float(op[2]), float(op[3]), float(op[4])))
    return tuple(runs), tuple(rules)


def _pieces(prefix: str, parts: tuple[tuple[str, str], ...]) -> tuple[object, ...]:
    pieces: list[object] = [("t", char) for char in prefix]
    for kind, value in parts:
        if kind == "math":
            pieces.append(("m", value))
        else:
            pieces.extend(("t", char) for char in value)
    return tuple(pieces)


def _wrap_pieces(
    pieces: tuple[object, ...], size: float, first_width: float, width: float
) -> list[LineBox]:
    lines: list[LineBox] = []
    glyphs: list[Glyph] = []
    rules: list[Rule] = []
    used = 0.0
    ascent = size * 0.8
    descent = size * 0.2
    limit = first_width

    def flush() -> None:
        nonlocal glyphs, rules, used, ascent, descent, limit
        if glyphs or rules:
            lines.append(LineBox(tuple(glyphs), tuple(rules), ascent, descent))
        glyphs = []
        rules = []
        used = 0.0
        ascent = size * 0.8
        descent = size * 0.2
        limit = width

    for kind, value in pieces:
        if kind == "t":
            char = str(value)
            advance = size if ord(char) > 0x2E80 else size / 2
            if glyphs and used + advance > limit:
                flush()
            glyphs.append(Glyph(char, used, 0.0, size, _font(char), 1.0))
            used += advance
            continue
        box = layout_math(str(value), size)
        if box.width > width:
            raise FormulaFault("formula_too_wide", "")
        if not glyphs and not rules and box.width > limit and limit < width:
            lines.append(LineBox((), (), size * 0.8, size * 0.2))
            limit = width
        elif glyphs and used + box.width > limit:
            flush()
        for glyph in box.glyphs:
            glyphs.append(Glyph(glyph.text, used + glyph.x, glyph.y, glyph.size, glyph.font, glyph.scale_y))
        for rule in box.rules:
            rules.append(Rule(used + rule.x1, rule.y1, used + rule.x2, rule.y2))
        used += box.width
        ascent = max(ascent, box.ascent)
        descent = max(descent, box.descent)
    flush()
    return lines


def _font(char: str) -> str:
    if char in _OPERATORS or ord(char) > 0x7F:
        return "cjk"
    return "latin"


def _advance(char: str, size: float) -> float:
    if char in ".,":
        return size * 0.28
    if char in "()[]|":
        return size * 0.4
    if _font(char) == "cjk" and ord(char) > 0x2E80:
        return size
    if _font(char) == "cjk":
        return size * 0.6
    return size * 0.5


class _Cur:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    def _skip(self) -> None:
        while self.i < len(self.text) and self.text[self.i] == " ":
            self.i += 1

    def peek(self) -> str:
        self._skip()
        if self.i >= len(self.text):
            return ""
        return self.text[self.i]

    def take(self) -> str:
        self._skip()
        if self.i >= len(self.text):
            return ""
        char = self.text[self.i]
        self.i += 1
        return char

    def command(self) -> str:
        if self.take() != "\\":
            raise FormulaFault("formula_unsupported", "")
        if self.i >= len(self.text):
            raise FormulaFault("formula_unsupported", "\\")
        start = self.i
        if self.text[self.i].isalpha():
            while self.i < len(self.text) and self.text[self.i].isalpha():
                self.i += 1
        else:
            self.i += 1
        return self.text[start : self.i]

    def starts(self, token: str) -> bool:
        self._skip()
        return self.text.startswith(token, self.i)


def _parse(latex: str) -> tuple[object, ...]:
    missing = unsupported_commands(latex)
    if missing:
        raise FormulaFault("formula_unsupported", missing[0])
    return _sequence(_Cur(latex), "")


def _sequence(cur: _Cur, stop: str) -> tuple[object, ...]:
    nodes: list[object] = []
    while True:
        if stop == "}" and cur.peek() == "}":
            break
        if stop == "|" and cur.peek() == "|":
            break
        if stop == "right" and cur.starts("\\right"):
            break
        if cur.peek() == "":
            if stop:
                raise FormulaFault("formula_unsupported", "\\" + stop if stop != "}" else "}")
            break
        node = _one(cur, stop)
        if node is None:
            break
        nodes.append(_scripts(cur, node))
    return tuple(nodes)


def _one(cur: _Cur, stop: str) -> object | None:
    char = cur.peek()
    if char == "":
        return None
    if char == "\\" :
        name = cur.command()
        if name in {"frac", "dfrac", "tfrac"}:
            return ("frac", _group(cur), _group(cur))
        if name == "left":
            opener = _delimiter(cur)
            inner = _sequence(cur, "right")
            if not cur.starts("\\right"):
                raise FormulaFault("formula_unsupported", "\\right")
            cur.command()
            closer = _delimiter(cur)
            return ("delim", opener, inner, closer)
        if name == "textcircled":
            number = _circled_number(_group(cur))
            if number is None:
                raise FormulaFault("formula_unsupported", "\\textcircled")
            return ("sym", chr(0x2460 + number - 1))
        if name in {"text", "mathrm"}:
            return ("row", _group(cur))
        if name == "%":
            return ("sym", "%")
        if name in _SPACES:
            return ("sp", _SPACES[name])
        if name in _SYMBOLS:
            return ("sym", _SYMBOLS[name])
        raise FormulaFault("formula_unsupported", "\\" + name)
    if char == "{":
        return ("row", _group(cur))
    if char == "|":
        if stop == "|":
            return None
        cur.take()
        inner = _sequence(cur, "|")
        if cur.take() != "|":
            raise FormulaFault("formula_unsupported", "|")
        return ("delim", "|", inner, "|")
    if char in "^_}":
        raise FormulaFault("formula_unsupported", char)
    if char == "~":
        cur.take()
        return ("sp", _SPACES["~"])
    return ("ch", cur.take())


def _scripts(cur: _Cur, node: object) -> object:
    sup: object | None = None
    sub: object | None = None
    while cur.peek() in {"^", "_"}:
        mark = cur.take()
        body: object = _script_body(cur)
        if mark == "^":
            sup = body
        else:
            sub = body
    if sup is None and sub is None:
        return node
    return ("script", node, sup, sub)


def _script_body(cur: _Cur) -> object:
    if cur.peek() == "{":
        return ("row", _group(cur))
    one = _one(cur, "")
    if one is None:
        raise FormulaFault("formula_unsupported", "^")
    return one


def _circled_number(nodes: tuple[object, ...]) -> int | None:
    """1 through 20. Anything else is unsupported. The glyph is U+2460 plus the index."""
    digits: list[str] = []
    for node in nodes:
        if not isinstance(node, tuple) or len(node) < 2 or node[0] != "ch":
            return None
        char = node[1]
        if not isinstance(char, str) or len(char) != 1 or not char.isdigit():
            return None
        digits.append(char)
    if not digits:
        return None
    number = int("".join(digits))
    if number < 1 or number > 20:
        return None
    return number


def _group(cur: _Cur) -> tuple[object, ...]:
    if cur.take() != "{":
        raise FormulaFault("formula_unsupported", "{")
    inner = _sequence(cur, "}")
    if cur.take() != "}":
        raise FormulaFault("formula_unsupported", "}")
    return inner


def _delimiter(cur: _Cur) -> str:
    if cur.peek() == "\\":
        name = cur.command()
        if name in {"{", "}"}:
            return name
        if name == "|":
            return "|"
        raise FormulaFault("formula_unsupported", "\\" + name)
    char = cur.take()
    if char not in "()[]|.":
        raise FormulaFault("formula_unsupported", char or "\\left")
    return char


def _hbox(nodes: tuple[object, ...], size: float) -> FormulaBox:
    glyphs: list[Glyph] = []
    rules: list[Rule] = []
    width = 0.0
    ascent = size * 0.75
    descent = size * 0.2
    for node in nodes:
        box = _node(node, size)
        glyphs.extend(_shift(box.glyphs, width, 0.0))
        rules.extend(Rule(rule.x1 + width, rule.y1, rule.x2 + width, rule.y2) for rule in box.rules)
        width += box.width
        ascent = max(ascent, box.ascent)
        descent = max(descent, box.descent)
    if not nodes:
        ascent = size * 0.75
        descent = size * 0.2
    return FormulaBox(tuple(glyphs), tuple(rules), width, ascent, descent)


def _node(node: object, size: float) -> FormulaBox:
    kind = node[0]  # type: ignore[index]
    if kind == "ch":
        return _char(node[1], size)  # type: ignore[index]
    if kind == "sym":
        return _char(node[1], size)  # type: ignore[index]
    if kind == "sp":
        return FormulaBox((), (), size * float(node[1]), size * 0.2, 0.0)  # type: ignore[index]
    if kind == "row":
        return _hbox(node[1], size)  # type: ignore[index]
    if kind == "frac":
        return _fraction(node[1], node[2], size)  # type: ignore[index]
    if kind == "script":
        return _script(node[1], node[2], node[3], size)  # type: ignore[index]
    if kind == "delim":
        return _delim(str(node[1]), node[2], str(node[3]), size)  # type: ignore[index]
    raise FormulaFault("formula_unsupported", "")


def _char(char: str, size: float) -> FormulaBox:
    glyph = Glyph(char, 0.0, 0.0, size, _font(char), 1.0)
    descent = size * 0.25 if char in "()[]" else size * 0.2
    return FormulaBox((glyph,), (), _advance(char, size), size * 0.75, descent)


def _fraction(num_nodes: tuple[object, ...], den_nodes: tuple[object, ...], size: float) -> FormulaBox:
    num = _hbox(num_nodes, size)
    den = _hbox(den_nodes, size)
    gap = size * FRACTION_GAP
    axis = size * FRACTION_AXIS
    inner = max(num.width, den.width)
    pad = size * 0.2
    width = inner + pad
    num_y = axis + gap + num.descent
    den_y = axis - gap - den.ascent
    glyphs = _shift(num.glyphs, (width - num.width) / 2, num_y) + _shift(den.glyphs, (width - den.width) / 2, den_y)
    rule = Rule(pad / 2, axis, width - pad / 2, axis)
    rules = _shift_rules(num.rules, (width - num.width) / 2, num_y)
    rules += _shift_rules(den.rules, (width - den.width) / 2, den_y)
    rules.append(rule)
    ascent = num_y + num.ascent
    descent = -(den_y - den.descent)
    return FormulaBox(tuple(glyphs), tuple(rules), width, ascent, descent)


def _script(base: object, sup: object | None, sub: object | None, size: float) -> FormulaBox:
    body = _node(base, size)
    sup_box = _node(sup, size * SCRIPT_SCALE) if sup is not None else None
    sub_box = _node(sub, size * SCRIPT_SCALE) if sub is not None else None
    rise = size * SUPERSCRIPT_RISE
    drop = size * SUBSCRIPT_DROP
    glyphs = list(body.glyphs)
    rules = list(body.rules)
    extra = 0.0
    ascent = body.ascent
    descent = body.descent
    if sup_box is not None:
        glyphs.extend(_shift(sup_box.glyphs, body.width, rise))
        rules.extend(_shift_rules(sup_box.rules, body.width, rise))
        extra = max(extra, sup_box.width)
        ascent = max(ascent, rise + sup_box.ascent)
    if sub_box is not None:
        glyphs.extend(_shift(sub_box.glyphs, body.width, -drop))
        rules.extend(_shift_rules(sub_box.rules, body.width, -drop))
        extra = max(extra, sub_box.width)
        descent = max(descent, drop + sub_box.descent)
    return FormulaBox(tuple(glyphs), tuple(rules), body.width + extra, ascent, descent)


def _delim(opener: str, inner_nodes: object, closer: str, size: float) -> FormulaBox:
    inner = _hbox(inner_nodes, size)  # type: ignore[arg-type]
    content = max(inner.ascent + inner.descent, size)
    side = size * 0.4
    glyphs = list(_shift(inner.glyphs, side if opener != "." else 0.0, 0.0))
    rules = _shift_rules(inner.rules, side if opener != "." else 0.0, 0.0)
    scale = content / (size * 0.7)
    width = inner.width
    if opener != ".":
        if opener == "|":
            rules.append(Rule(side * 0.5, -inner.descent, side * 0.5, inner.ascent))
        else:
            glyphs.insert(0, Glyph(opener, 0.0, 0.0, size, "latin", scale))
        width += side
    if closer != ".":
        x = width
        if closer == "|":
            rules.append(Rule(x + side * 0.5, -inner.descent, x + side * 0.5, inner.ascent))
        else:
            glyphs.append(Glyph(closer, x, 0.0, size, "latin", scale))
        width += side
    return FormulaBox(tuple(glyphs), tuple(rules), width, inner.ascent, inner.descent)


def _shift(glyphs: tuple[Glyph, ...], dx: float, dy: float) -> tuple[Glyph, ...]:
    return tuple(
        Glyph(glyph.text, glyph.x + dx, glyph.y + dy, glyph.size, glyph.font, glyph.scale_y) for glyph in glyphs
    )


def _shift_rules(rules: tuple[Rule, ...], dx: float, dy: float) -> list[Rule]:
    return [Rule(rule.x1 + dx, rule.y1 + dy, rule.x2 + dx, rule.y2 + dy) for rule in rules]
