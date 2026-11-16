"""Approve and publish one question version. Refusal is Err, not an exception."""

from __future__ import annotations

import time
from dataclasses import replace

from backend.catalog.api import ApprovalPort
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store


class ApprovalWriter(ApprovalPort):
    def put(self, snapshot: ApprovalSnapshot) -> None:
        """Store the snapshot. A later put with the same question id replaces it."""


def publish_version(
    question_version_id: str,
    approvals: ApprovalWriter,
    logger: Logger,
    request_id: str,
) -> Ok[ApprovalSnapshot] | Err:
    """Mark the question and the answer approved. A retired version stays retired."""
    started = time.perf_counter()
    loaded = read_store(
        lambda: approvals.read_snapshot(question_version_id),
        logger,
        request_id,
        "catalog.publish",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    snapshot = loaded.value
    if snapshot is None:
        return _refuse(logger, request_id, started, "not_found", "the question version does not exist")
    if snapshot.retired:
        return _refuse(logger, request_id, started, "retired", "the question version is retired")
    if snapshot.question_approved and snapshot.answer_approved:
        return Ok(snapshot)
    updated = replace(snapshot, question_approved=True, answer_approved=True)
    saved = read_store(
        lambda: approvals.put(updated),
        logger,
        request_id,
        "catalog.publish",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="question_published",
        request_id=request_id,
        module="catalog.publish",
        outcome=updated.question_version_id,
        started=started,
    )
    return Ok(updated)


def retire_version(
    question_version_id: str,
    approvals: ApprovalWriter,
    logger: Logger,
    request_id: str,
) -> Ok[ApprovalSnapshot] | Err:
    """Mark the publication retired. Papers already stored keep their file id."""
    started = time.perf_counter()
    loaded = read_store(
        lambda: approvals.read_snapshot(question_version_id),
        logger,
        request_id,
        "catalog.publish",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    snapshot = loaded.value
    if snapshot is None:
        return _refuse(logger, request_id, started, "not_found", "the question version does not exist")
    updated = replace(snapshot, retired=True)
    saved = read_store(
        lambda: approvals.put(updated),
        logger,
        request_id,
        "catalog.publish",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="question_published",
        request_id=request_id,
        module="catalog.retire",
        outcome=updated.question_version_id,
        started=started,
    )
    return Ok(updated)


def revise_text(
    question_version_id: str,
    stem: str,
    answer_text: str,
    approvals: ApprovalWriter,
    logger: Logger,
    request_id: str,
) -> Ok[ApprovalSnapshot] | Err:
    """Change the bank text. Papers that already stored a file keep that file id."""
    started = time.perf_counter()
    loaded = read_store(
        lambda: approvals.read_snapshot(question_version_id),
        logger,
        request_id,
        "catalog.revise",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    snapshot = loaded.value
    if snapshot is None:
        return _refuse(logger, request_id, started, "not_found", "the question version does not exist")
    updated = replace(snapshot, stem=stem, answer_text=answer_text)
    saved = read_store(
        lambda: approvals.put(updated),
        logger,
        request_id,
        "catalog.revise",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="question_published",
        request_id=request_id,
        module="catalog.revise",
        outcome=updated.question_version_id,
        started=started,
    )
    return Ok(updated)


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module="catalog.publish",
        outcome=code,
        started=started,
    )
    return Err(code, message)
