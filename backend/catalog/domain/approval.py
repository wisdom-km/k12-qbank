"""R1: a formal paper needs an approved question version and answer version."""

from __future__ import annotations

from backend.catalog.domain.snapshot import ApprovalSnapshot, IssueSnapshot
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


def copy_issue_snapshot(snapshot: ApprovalSnapshot) -> IssueSnapshot | Err:
    """Copy the version ids that a paper must freeze. Empty ids are not a freeze."""
    if not snapshot.question_version_id.strip() or not snapshot.answer_version_id.strip():
        return Err(
            "not_frozen",
            "the question version and the answer version must both be copied",
        )
    return IssueSnapshot(
        question_version_id=snapshot.question_version_id,
        answer_version_id=snapshot.answer_version_id,
        asset_ids=tuple(snapshot.asset_ids),
        layout_template_id=snapshot.layout_template_id,
    )
