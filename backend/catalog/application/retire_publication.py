"""Retire one publication binding. Only a real retirement is audited."""

from __future__ import annotations

import json
import time

from backend.catalog.api import Publications
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger


def retire_publication(
    publications: Publications,
    q_vid: str,
    a_vid: str,
    actor: str | None,
    logger: Logger,
    request_id: str | None = None,
) -> str:
    """Return retired, already_retired, or not_found. request_id stays off the port."""
    code = publications.retire_by_binding(q_vid, a_vid, actor)
    if code != "retired":
        return code
    rows = [row for row in publications.rows_for(q_vid, a_vid) if row.status == "retired"]
    row = rows[0]
    detail = {
        "question_version_id": row.question_version_id,
        "answer_version_id": row.answer_version_id,
        "subject_id": row.subject_id,
        "before": {"status": "active"},
        "after": {"status": "retired"},
    }
    logger.log(
        LogEvent(
            time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            level="INFO",
            event="publication_retired",
            request_id="" if request_id is None else request_id,
            module="catalog.publication",
            outcome="ok",
            duration_ms=0,
            actor_user_id="" if actor is None else actor,
            target_kind="publication",
            target_id=row.publication_id,
            audit=True,
            action="publication_retired",
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )
    return code
