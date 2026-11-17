"""Store one review-tool answer file. The parsed object is the future row."""

from __future__ import annotations

import time
from typing import Protocol

from backend.catalog.domain.answer import AnswerDraft, parse_answer_draft
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store


class AnswerWriter(Protocol):
    def put(self, answer: AnswerDraft) -> str | None:
        """Store one answer. Return another key when a second applicable row is refused."""


def import_answer_draft(
    payload: object,
    store: AnswerWriter,
    logger: Logger,
    request_id: str,
) -> Ok[AnswerDraft] | Err:
    """Accept one answer file as it is. A page block list is refused."""
    started = time.perf_counter()
    parsed = parse_answer_draft(payload)
    if isinstance(parsed, Err):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="catalog.import_answer",
            outcome=parsed.code,
            started=started,
        )
        return parsed
    saved = read_store(
        lambda: store.put(parsed.value),
        logger,
        request_id,
        "catalog.import_answer",
        started,
    )
    if isinstance(saved, Err):
        return saved
    if saved.value is not None:
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="catalog.import_answer",
            outcome="answer_conflict",
            started=started,
        )
        return Err("answer_conflict", "this question already has an applicable answer")
    emit(
        logger,
        level="INFO",
        event="answer_imported",
        request_id=request_id,
        module="catalog.import_answer",
        outcome="1",
        started=started,
    )
    return parsed
