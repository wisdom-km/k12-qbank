"""Store one review-tool draft file. The parsed object is the future row."""

from __future__ import annotations

import time
from typing import Protocol

from backend.catalog.domain.draft import DraftFile, parse_question_draft
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store


class DraftWriter(Protocol):
    def save(self, draft: DraftFile) -> None:
        """Replace stored drafts with this file. Do not publish them."""


def import_question_draft(
    payload: object,
    store: DraftWriter,
    logger: Logger,
    request_id: str,
) -> Ok[DraftFile] | Err:
    """Accept the review file as it is. A page block list is refused."""
    started = time.perf_counter()
    parsed = parse_question_draft(payload)
    if isinstance(parsed, Err):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="catalog.import_draft",
            outcome=parsed.code,
            started=started,
        )
        return parsed
    saved = read_store(
        lambda: store.save(parsed.value),
        logger,
        request_id,
        "catalog.import_draft",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="draft_imported",
        request_id=request_id,
        module="catalog.import_draft",
        outcome=str(len(parsed.value.questions)),
        started=started,
    )
    return parsed
