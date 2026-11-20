"""Child rows written in the same transaction as the parent. SQL stays here."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg.types.json import Json


class PgSubQuestions:
    def insert(self, conn: Any, question_id: str, rows: list[dict[str, object]]) -> None:
        for position, item in enumerate(rows, start=1):
            sub_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO sub_question (
                    sub_question_id, question_id, position, number, stem, type, structure
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sub_id,
                    question_id,
                    position,
                    item["number"],
                    _json(item["stem"]),
                    item.get("type"),
                    item.get("structure"),
                ),
            )
            options = item.get("options")
            PgQuestionOptions().insert(conn, question_id, sub_id, _rows(options))


class PgQuestionOptions:
    def insert(
        self,
        conn: Any,
        question_id: str,
        sub_question_id: str | None,
        rows: list[dict[str, object]],
    ) -> None:
        for position, item in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO question_option (
                    question_option_id, question_id, sub_question_id, position, key, content
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    question_id,
                    sub_question_id,
                    position,
                    item["key"],
                    _json(item["content"]),
                ),
            )


class PgQuestionAssets:
    def insert(self, conn: Any, question_id: str, rows: list[dict[str, object]]) -> None:
        _crops(
            conn,
            """
            INSERT INTO question_asset (
                question_asset_id, question_id, position, role, bbox
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            question_id,
            rows,
        )


class PgAnswerParts:
    def insert(self, conn: Any, answer_id: str, rows: list[dict[str, object]]) -> None:
        for item in rows:
            conn.execute(
                """
                INSERT INTO answer_part (
                    answer_part_id, answer_id, sub_key, role, "order", content
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    answer_id,
                    item["sub_key"],
                    item["role"],
                    item["order"],
                    _json(item["content"]),
                ),
            )


class PgAnswerAssets:
    def insert(self, conn: Any, answer_id: str, rows: list[dict[str, object]]) -> None:
        _crops(
            conn,
            """
            INSERT INTO answer_asset (
                answer_asset_id, answer_id, position, role, bbox
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            answer_id,
            rows,
        )


def write_question_children(
    conn: Any,
    question_id: str,
    options: list[dict[str, object]],
    subquestions: list[dict[str, object]],
    assets: list[dict[str, object]],
) -> None:
    PgSubQuestions().insert(conn, question_id, subquestions)
    PgQuestionOptions().insert(conn, question_id, None, options)
    PgQuestionAssets().insert(conn, question_id, assets)


def write_answer_children(
    conn: Any,
    answer_id: str,
    parts: list[dict[str, object]],
    assets: list[dict[str, object]],
) -> None:
    PgAnswerParts().insert(conn, answer_id, parts)
    PgAnswerAssets().insert(conn, answer_id, assets)


def _crops(conn: Any, statement: str, parent_id: str, rows: list[dict[str, object]]) -> None:
    for position, item in enumerate(rows, start=1):
        conn.execute(
            statement,
            (str(uuid.uuid4()), parent_id, position, item["role"], _json(item["bbox"])),
        )


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _json(value: object) -> Json:
    return Json(value, dumps=lambda item: json.dumps(item, ensure_ascii=False))
