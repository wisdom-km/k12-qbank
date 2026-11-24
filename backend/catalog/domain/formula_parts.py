"""Structured stem and option fragments. NULL means the row was never split."""

from __future__ import annotations

import json


def draft_stem_parts(parts: tuple[object, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(_one(part) for part in parts)


def draft_option_parts(
    options: tuple[object, ...],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for option in options:
        key = str(getattr(option, "key", ""))
        content = getattr(option, "content", ())
        rows.append((key, tuple(_one(part) for part in content)))
    return tuple(rows)


def stem_json(parts: tuple[tuple[str, str], ...] | None) -> list[dict[str, str]] | None:
    if parts is None:
        return None
    return [_fragment(kind, value) for kind, value in parts]


def option_json(
    parts: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None,
) -> list[dict[str, object]] | None:
    if parts is None:
        return None
    return [{"key": key, "content": stem_json(content)} for key, content in parts]


def stem_from_json(value: object) -> tuple[tuple[str, str], ...] | None:
    raw = _load(value)
    if raw is None:
        return None
    rows: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "math":
            rows.append(("math", str(item.get("latex", ""))))
        else:
            rows.append(("text", str(item.get("value", ""))))
    return tuple(rows)


def option_from_json(value: object) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...] | None:
    raw = _load(value)
    if raw is None:
        return None
    rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = stem_from_json(item.get("content"))
        rows.append((str(item.get("key", "")), () if content is None else content))
    return tuple(rows)


def _one(part: object) -> tuple[str, str]:
    value = getattr(part, "value", None)
    if isinstance(value, str):
        return ("text", value)
    latex = getattr(part, "latex", None)
    if isinstance(latex, str):
        return ("math", latex)
    return ("text", "")


def _fragment(kind: str, value: str) -> dict[str, str]:
    if kind == "math":
        return {"type": "math", "latex": value}
    return {"type": "text", "value": value}


def _load(value: object) -> list[object] | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value == "":
            return None
        loaded = json.loads(value)
    else:
        loaded = value
    if not isinstance(loaded, list):
        return None
    return loaded
