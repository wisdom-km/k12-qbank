"""Retire one publication binding. Only a real retirement is audited."""

from __future__ import annotations

import json
import time

from backend.catalog.api import Publications
from backend.catalog.domain.publication import RetireCode
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
        return str(code)
    if not isinstance(code, RetireCode) or code.publication_id is None or code.subject_id is None:
        raise RuntimeError("retire did not name the publication row")
    detail = {
        "question_version_id": q_vid,
        "answer_version_id": a_vid,
        "subject_id": code.subject_id,
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
            target_id=code.publication_id,
            audit=True,
            action="publication_retired",
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )
    return "retired"
