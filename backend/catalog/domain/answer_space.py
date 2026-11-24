"""Answer-space size belongs to the question. NULL in the row means the type default."""

from __future__ import annotations

SPACES = ("letter", "blanks", "small", "medium", "large", "full")

_BY_TYPE = {
    "single_choice": "letter",
    "multiple_choice": "letter",
    "fill_blank": "blanks",
    "solution": "large",
    "composite": "large",
    "unresolved": "medium",
}


def default_space(question_type: str) -> str:
    """The size used when the approval row stores nothing."""
    return _BY_TYPE.get(question_type, "medium")


def resolved_space(stored: str | None, question_type: str) -> tuple[str, bool]:
    """Return the size to print, and whether it came from the type default."""
    if stored:
        return stored, False
    return default_space(question_type), True
