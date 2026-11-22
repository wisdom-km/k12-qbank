"""Publish one binding. Only a real insert is audited."""

from __future__ import annotations

import json
import time

from backend.catalog.api import Publications
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger


def publish_publication(
    publications: Publications,
    question_version_id: str,
    answer_version_id: str,
    actor: str | None,
    logger: Logger,
    layout_template_id: str | None = None,
    request_id: str | None = None,
) -> str:
    """Return published, already_active, or not_approved. request_id stays off the port."""
    code = publications.publish_by_binding(
        question_version_id,
        answer_version_id,
        actor,  # type: ignore[arg-type]
        layout_template_id,
    )
    if code != "published":
        return code
    rows = publications.rows_for(question_version_id, answer_version_id)
    active = [row for row in rows if row.status == "active"]
    row = active[0]
    detail = {
        "question_version_id": row.question_version_id,
        "answer_version_id": row.answer_version_id,
        "subject_id": row.subject_id,
        "layout_template_id": row.layout_template_id,
        "sequence": len(rows),
        "after": {"status": "active"},
    }
    logger.log(
        LogEvent(
            time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            level="INFO",
            event="publication_published",
            request_id="" if request_id is None else request_id,
            module="catalog.publication",
            outcome="ok",
            duration_ms=0,
            actor_user_id="" if actor is None else actor,
            target_kind="publication",
            target_id=row.publication_id,
            audit=True,
            action="publication_published",
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )
    return code
