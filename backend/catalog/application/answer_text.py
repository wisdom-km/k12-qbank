"""Plain answer text for a new import. Content-only answers stay as they were."""

from __future__ import annotations

from backend.catalog.domain.answer import AnswerDraft


def plain_parts(parts: tuple[object, ...]) -> str:
    """Join text and math. The same join the snapshot used before parts were included."""
    chunks: list[str] = []
    for part in parts:
        value = getattr(part, "value", None)
        latex = getattr(part, "latex", None)
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(latex, str):
            chunks.append(latex)
    return "".join(chunks)


def answer_plain(answer: AnswerDraft) -> str:
    """Content, then each sub-question. Steps follow their sub-question in order."""
    base = plain_parts(answer.content)
    if not answer.parts:
        return base
    groups: dict[str, list[object]] = {}
    order: list[str] = []
    for part in sorted(answer.parts, key=lambda item: item.order):
        if part.sub_key not in groups:
            order.append(part.sub_key)
            groups[part.sub_key] = []
        groups[part.sub_key].append(part)
    pieces: list[str] = []
    for key in order:
        body = "".join(plain_parts(part.content) for part in groups[key])
        label = key if key.startswith("(") and key.endswith(")") else "(" + key + ")"
        pieces.append((label + " " + body).rstrip())
    joined = "；".join(pieces)
    if base:
        return base + "；" + joined
    return joined
