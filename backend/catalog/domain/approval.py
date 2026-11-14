"""R1: a formal paper needs an approved question version and answer version."""

from __future__ import annotations

from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.kernel.result import Err


def issue_block(snapshot: ApprovalSnapshot | None) -> Err | None:
    if snapshot is None:
        return Err("not_found", "the question version does not exist")
    if snapshot.retired:
        return Err("retired", "the question version is retired")
    if not snapshot.question_approved or not snapshot.answer_approved:
        return Err(
            "not_approved",
            "the question version and the answer version must both be approved",
        )
    return None
