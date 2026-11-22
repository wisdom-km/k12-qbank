"""One published binding. layout_template_id stays empty in this batch."""

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
