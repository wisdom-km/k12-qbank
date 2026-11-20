"""PostgreSQL answer rows. Field names match the v1 draft. SQL stays here."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from psycopg.types.json import Json

from backend.catalog.adapters.pg_children import write_answer_children
from backend.catalog.domain.answer import (
    CONTRACT,
    CONTRACT_VERSION,
    AnswerAsset,
    AnswerDraft,
    AnswerPart,
    MathPart,
    TextPart,
    parse_answer_draft,
)
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.result import Err, StoreFault

T = TypeVar("T")

_INSERT = """
INSERT INTO answers (
    answer_id, question_id, version,
    contract, contract_version, schema_version, ok, reason,
    question_key, key, origin, status, applicable,
    source, content, parts, assets
) VALUES (
    %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s
)
"""


class PgAnswers:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def put(self, answer: AnswerDraft) -> str | None:
        return _run(self._pool, lambda conn: _put(conn, answer))

    def read(self, key: str) -> AnswerDraft | None:
        return _run(self._pool, lambda conn: _read(conn, key))


def insert_approved_answer(conn: Any, snapshot: ApprovalSnapshot) -> None:
    """Insert the approved answer once. origin teacher is the snapshot's only source."""
    key = f"{snapshot.question_version_id}:teacher:1"
    conn.execute(
        _INSERT,
        _values(
            snapshot.answer_version_id,
            snapshot.question_version_id,
            1,
            snapshot.question_version_id,
            key,
            "teacher",
            "confirmed",
            True,
            {},
            [{"type": "text", "value": snapshot.answer_text}],
            [],
            [],
            True,
            "",
        ),
    )
    write_answer_children(conn, snapshot.answer_version_id, [], [])


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _put(conn: Any, answer: AnswerDraft) -> str | None:
    current = _applicable_key(conn, answer.question_key)
    if answer.applicable and current is not None and current != answer.key:
        return current
    if current == answer.key:
        _clear_applicable(conn, answer.key)
    question_id = _question_id(conn, answer.question_key)
    if question_id is None:
        raise StoreFault("store_failed")
    version = _next_version(conn, answer.key)
    answer_id = str(uuid.uuid4())
    parts = [_part(item) for item in answer.parts]
    assets = [_asset(item) for item in answer.assets]
    conn.execute(_INSERT, _values_for(answer, question_id, version, answer_id, parts, assets))
    write_answer_children(conn, answer_id, parts, assets)
    return None


def _values_for(
    answer: AnswerDraft,
    question_id: str,
    version: int,
    answer_id: str,
    parts: list[object],
    assets: list[object],
) -> tuple[object, ...]:
    return _values(
        answer_id,
        question_id,
        version,
        answer.question_key,
        answer.key,
        answer.origin,
        answer.status,
        answer.applicable,
        _source(answer),
        _fragments(answer.content),
        parts,
        assets,
        answer.ok,
        answer.reason,
    )


def _values(
    answer_id: str,
    question_id: str,
    version: int,
    question_key: str,
    key: str,
    origin: str,
    status: str,
    applicable: bool,
    source: dict[str, object],
    content: list[object],
    parts: list[object],
    assets: list[object],
    ok: bool,
    reason: str,
) -> tuple[object, ...]:
    return (
        answer_id,
        question_id,
        version,
        CONTRACT,
        CONTRACT_VERSION,
        1,
        ok,
        reason,
        question_key,
        key,
        origin,
        status,
        applicable,
        _json(source),
        _json(content),
        _json(parts),
        _json(assets),
    )


def _read(conn: Any, key: str) -> AnswerDraft | None:
    row = conn.execute(
        """
        SELECT ok, reason, question_key, key, origin, status, applicable, source, content, parts, assets
        FROM answers
        WHERE key = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if row is None:
        return None
    parsed = parse_answer_draft(_payload(row))
    if isinstance(parsed, Err):
        raise StoreFault("store_failed")
    return parsed.value


def _payload(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "contract": CONTRACT,
        "contract_version": CONTRACT_VERSION,
        "schema_version": 1,
        "ok": row[0],
        "reason": row[1],
        "question_key": row[2],
        "key": row[3],
        "origin": row[4],
        "status": row[5],
        "applicable": row[6],
        "source": row[7],
        "content": row[8],
        "parts": row[9],
        "assets": row[10],
    }


def _applicable_key(conn: Any, question_key: str) -> str | None:
    row = conn.execute(
        """
        SELECT key FROM answers
        WHERE question_key = %s AND applicable
        ORDER BY version DESC
        LIMIT 1
        """,
        (question_key,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _clear_applicable(conn: Any, key: str) -> None:
    conn.execute("UPDATE answers SET applicable = false WHERE key = %s AND applicable", (key,))


def _question_id(conn: Any, question_key: str) -> str | None:
    row = conn.execute(
        """
        SELECT question_id FROM questions
        WHERE key = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (question_key,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _next_version(conn: Any, key: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM answers WHERE key = %s", (key,)).fetchone()
    return int(row[0]) + 1


def _source(answer: AnswerDraft) -> dict[str, object]:
    if answer.origin == "ocr":
        return {"pdf_page": answer.pdf_page}
    if answer.origin == "model":
        return {"model_task_id": answer.model_task_id or ""}
    return {}


def _fragments(parts: tuple[TextPart | MathPart, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for part in parts:
        if isinstance(part, TextPart):
            rows.append({"type": "text", "value": part.value})
        else:
            rows.append({"type": "math", "latex": part.latex})
    return rows


def _part(item: AnswerPart) -> dict[str, object]:
    return {
        "sub_key": item.sub_key,
        "role": item.role,
        "order": item.order,
        "content": _fragments(item.content),
    }


def _asset(item: AnswerAsset) -> dict[str, object]:
    return {"role": "crop", "bbox": list(item.bbox)}


def _json(value: object) -> Json:
    return Json(value, dumps=lambda item: json.dumps(item, ensure_ascii=False))
