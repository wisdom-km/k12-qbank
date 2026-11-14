"""Read one approval snapshot. Refusal is Err, not an exception."""

from __future__ import annotations

import time

from backend.catalog.api import ApprovalPort
from backend.kernel.use_log import emit, read_store
from backend.catalog.domain.approval import issue_block
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok


def read_snapshot(
    question_version_id: str,
    approvals: ApprovalPort,
    logger: Logger,
    request_id: str,
) -> Ok[ApprovalSnapshot] | Err:
    started = time.perf_counter()
    loaded = read_store(
        lambda: approvals.read_snapshot(question_version_id),
        logger,
        request_id,
        "catalog.read",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    blocked = issue_block(loaded.value)
    if blocked is not None:
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="catalog.read",
            outcome=blocked.code,
            started=started,
        )
        return blocked
    snapshot = loaded.value
    if snapshot is None:
        return Err("not_found", "the question version does not exist")
    return Ok(snapshot)
