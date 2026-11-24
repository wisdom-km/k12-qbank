"""PostgreSQL question rows. Field names match the v1 draft. SQL stays here."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar

from psycopg.types.json import Json

from backend.catalog.adapters.pg_children import write_question_children
from backend.catalog.domain.parse import parse_question_draft
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.catalog.domain.validate import (
    CONTRACT,
    CONTRACT_VERSION,
    GEOMETRY_KIND,
    TYPE_STRUCTURE,
    ChoiceOption,
    CropAsset,
    DraftFile,
    GeometrySlot,
    MathPart,
    QuestionDraft,
    SubQuestion,
    TextPart,
)
from backend.kernel.result import Err, StoreFault

T = TypeVar("T")

_INSERT = """
INSERT INTO questions (
    question_id, version, created_at, approved_at,
    contract, contract_version, schema_version, ok, reason, preface, source,
    key, section, number, type, structure, status,
    stem, options, subquestions, assets, geometry
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s
)
"""


class PgQuestions:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def save(self, draft: DraftFile) -> None:
        _run(self._pool, lambda conn: _save_file(conn, draft))

    def read(self, key: str) -> QuestionDraft | None:
        return _run(self._pool, lambda conn: _read(conn, key))


def insert_approved_question(conn: Any, snapshot: ApprovalSnapshot) -> bool:
    """Insert one approved row. An existing question_id is left unchanged.

    A snapshot without a real type does not invent unresolved.
    """
    pair = _approved_pair(snapshot)
    if pair is None or _exists(conn, snapshot.question_version_id):
        return False
    now = datetime.now(timezone.utc)
    stem = _approved_stem(snapshot)
    conn.execute(
        _INSERT,
        _values(
            snapshot.question_version_id,
            1,
            now,
            snapshot.question_version_id,
            "",
            "",
            pair[0],
            pair[1],
            "confirmed",
            stem,
            [],
            [],
            [],
            None,
            True,
            "",
            "",
            {"pdf_page": None},
        ),
    )
    write_question_children(conn, snapshot.question_version_id, [], [], [])
    return True


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _save_file(conn: Any, draft: DraftFile) -> None:
    now = datetime.now(timezone.utc)
    source = {"pdf_page": draft.pdf_page}
    for question in draft.questions:
        version = _next_version(conn, question.key)
        question_id = str(uuid.uuid4())
        options = [_option(item) for item in question.options]
        subquestions = [_sub(item) for item in question.subquestions]
        assets = [_asset(item) for item in question.assets]
        conn.execute(
            _INSERT,
            _values(
                question_id,
                version,
                now,
                question.key,
                question.section,
                question.number,
                question.type,
                question.structure,
                question.status,
                _fragments(question.stem),
                options,
                subquestions,
                assets,
                _geometry(question.geometry),
                draft.ok,
                draft.reason,
                draft.preface,
                source,
            ),
        )
        write_question_children(conn, question_id, options, subquestions, assets)


def _values(
    question_id: str,
    version: int,
    moment: datetime,
    key: str,
    section: str,
    number: str,
    type_code: str,
    structure: str,
    status: str,
    stem: list[object],
    options: list[object],
    subquestions: list[object],
    assets: list[object],
    geometry: dict[str, object] | None,
    ok: bool,
    reason: str,
    preface: str,
    source: dict[str, object],
) -> tuple[object, ...]:
    return (
        question_id,
        version,
        moment,
        moment,
        CONTRACT,
        CONTRACT_VERSION,
        1,
        ok,
        reason,
        preface,
        _json(source),
        key,
        section,
        number,
        type_code,
        structure,
        status,
        _json(stem),
        _json(options),
        _json(subquestions),
        _json(assets),
        None if geometry is None else _json(geometry),
    )


def _read(conn: Any, key: str) -> QuestionDraft | None:
    row = conn.execute(
        """
        SELECT contract, contract_version, schema_version, ok, reason, preface, source,
               key, section, number, type, structure, status,
               stem, options, subquestions, assets, geometry
        FROM questions
        WHERE key = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if row is None:
        return None
    parsed = parse_question_draft(_payload(row))
    if isinstance(parsed, Err) or not parsed.value.questions:
        raise StoreFault("store_failed")
    return parsed.value.questions[0]


def _payload(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "contract": row[0],
        "contract_version": row[1],
        "schema_version": row[2],
        "ok": row[3],
        "reason": row[4],
        "preface": row[5],
        "source": row[6],
        "questions": [
            {
                "key": row[7],
                "section": row[8],
                "number": row[9],
                "type": row[10],
                "structure": row[11],
                "status": row[12],
                "stem": row[13],
                "options": row[14],
                "subquestions": row[15],
                "assets": row[16],
                "geometry": row[17],
            }
        ],
    }


def _next_version(conn: Any, key: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM questions WHERE key = %s", (key,)).fetchone()
    return int(row[0]) + 1


def _approved_stem(snapshot: ApprovalSnapshot) -> list[dict[str, str]]:
    """A new approved row keeps the fragments. An old row stays one text piece."""
    if snapshot.stem_parts is None:
        return [{"type": "text", "value": snapshot.stem}]
    rows: list[dict[str, str]] = []
    for kind, value in snapshot.stem_parts:
        if kind == "math":
            rows.append({"type": "math", "latex": value})
        else:
            rows.append({"type": "text", "value": value})
    return rows


def _approved_pair(snapshot: ApprovalSnapshot) -> tuple[str, str] | None:
    if snapshot.type == "" or snapshot.type == "unresolved":
        return None
    if TYPE_STRUCTURE.get(snapshot.type) != snapshot.structure:
        return None
    return snapshot.type, snapshot.structure


def _exists(conn: Any, question_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM questions WHERE question_id = %s", (question_id,)).fetchone()
    return row is not None


def _fragments(parts: tuple[TextPart | MathPart, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for part in parts:
        if isinstance(part, TextPart):
            rows.append({"type": "text", "value": part.value})
        else:
            rows.append({"type": "math", "latex": part.latex})
    return rows


def _option(item: ChoiceOption) -> dict[str, object]:
    return {"key": item.key, "content": _fragments(item.content)}


def _sub(item: SubQuestion) -> dict[str, object]:
    body: dict[str, object] = {"number": item.number, "stem": _fragments(item.stem)}
    if item.type is None:
        return body
    body["type"] = item.type
    body["structure"] = item.structure
    if item.options:
        body["options"] = [_option(option) for option in item.options]
    return body


def _asset(item: CropAsset) -> dict[str, object]:
    return {"role": "crop", "bbox": list(item.bbox)}


def _geometry(slot: GeometrySlot | None) -> dict[str, object] | None:
    if slot is None:
        return None
    return {"kind": GEOMETRY_KIND, "version": 1, "document": json.loads(slot.document_json)}


def _json(value: object) -> Json:
    return Json(value, dumps=lambda item: json.dumps(item, ensure_ascii=False))
