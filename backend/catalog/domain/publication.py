"""One published binding. Explicit publish may store layout_template_id."""

from __future__ import annotations

from dataclasses import dataclass

from backend.kernel.result import StoreFault


@dataclass(frozen=True)
class Publication:
    publication_id: str
    question_version_id: str
    answer_version_id: str
    subject_id: str
    status: str
    layout_template_id: str | None = None


def require_actor(actor: str | None) -> None:
    """An empty actor never retires a binding and never reaches the audit sink."""
    if not isinstance(actor, str) or not actor.strip():
        raise StoreFault("invalid_actor")


def require_subject(subject_id: str | None) -> None:
    """The subject copied from the approval row must be non-empty."""
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise StoreFault("invalid_subject")


def bound_page(offset: int, limit: int) -> tuple[int, int]:
    """Clamp a list page. The numbers match the audit list: offset below 0 becomes 0, limit below 1 becomes 1, limit above 200 becomes 200."""
    if offset < 0:
        offset = 0
    if limit < 1:
        limit = 1
    elif limit > 200:
        limit = 200
    return offset, limit


def clean_layout(layout_template_id: str | None) -> str | None:
    """A blank layout is stored as NULL. There is no layout catalog yet."""
    if not isinstance(layout_template_id, str):
        return None
    text = layout_template_id.strip()
    if not text:
        return None
    return text
