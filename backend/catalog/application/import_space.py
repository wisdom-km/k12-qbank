"""Parse answer_space overrides from a book manifest. The use case owns the rules."""

from __future__ import annotations

from backend.catalog.domain.answer_space import SPACES

_KEYS = {"page", "key", "space"}


def parse_answer_space(raw: object) -> tuple[dict[tuple[int, str], str], str]:
    """Return overrides keyed by question page and original key, or a reason."""
    if raw is None:
        return {}, ""
    if not isinstance(raw, list):
        return {}, "unknown_field"
    found: dict[tuple[int, str], str] = {}
    for item in raw:
        if not isinstance(item, dict) or set(item) - _KEYS or set(_KEYS) - set(item):
            return {}, "unknown_field"
        page = item.get("page")
        key = item.get("key")
        space = item.get("space")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            return {}, "page_missing"
        if not isinstance(key, str) or not key.strip():
            return {}, "unknown_field"
        if not isinstance(space, str) or space not in SPACES:
            return {}, "invalid_answer_space"
        slot = (page, key)
        if slot in found:
            return {}, "duplicate_answer_space"
        found[slot] = space
    return found, ""
