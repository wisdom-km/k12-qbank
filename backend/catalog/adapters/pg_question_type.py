"""Copy a stored approval type onto an unresolved question. SQL stays here."""

from __future__ import annotations

from typing import Any

from backend.catalog.domain.validate import TYPE_STRUCTURE

_SCAN = """
SELECT q.question_id, a.type, a.structure
FROM questions q
LEFT JOIN approvals a ON a.question_version_id = q.question_id
WHERE q.type = 'unresolved'
"""

_UPDATE = """
UPDATE questions
SET type = %s, structure = %s
WHERE question_id = %s AND type = 'unresolved'
"""


def question_type_counts(conn: Any) -> dict[str, int]:
    scanned = 0
    skipped_missing = 0
    skipped_shape = 0
    for _question_id, code, structure in conn.execute(_SCAN):
        scanned += 1
        if code is None or code == "" or code == "unresolved":
            skipped_missing += 1
            continue
        if _pair(code, structure) is None:
            skipped_shape += 1
    eligible = scanned - skipped_missing - skipped_shape
    return {
        "scanned": scanned,
        "eligible": eligible,
        "skipped_missing": skipped_missing,
        "skipped_shape": skipped_shape,
    }


def apply_question_types(conn: Any) -> int:
    updated = 0
    for question_id, code, structure in conn.execute(_SCAN):
        pair = _pair(code, structure)
        if pair is None:
            continue
        result = conn.execute(_UPDATE, (pair[0], pair[1], question_id))
        updated += int(result.rowcount)
    return updated


def _pair(code: object, structure: object) -> tuple[str, str] | None:
    if not isinstance(code, str) or not isinstance(structure, str):
        return None
    if code == "" or code == "unresolved":
        return None
    if TYPE_STRUCTURE.get(code) != structure:
        return None
    return code, structure
