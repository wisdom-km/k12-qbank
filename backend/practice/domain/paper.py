"""R2: an issued paper keeps the version and asset ids from issue time."""

from __future__ import annotations

from dataclasses import dataclass

from backend.kernel.result import Err


@dataclass(frozen=True)
class Paper:
    """question_version_id and answer_version_id are the frozen issue-time copy."""

    paper_id: str
    teacher_id: str
    student_id: str
    subject_id: str
    question_version_id: str
    answer_version_id: str
    asset_ids: tuple[str, ...]
    layout_template_id: str
    review_version_id: str
    file_id: str | None
    status: str


def freeze_paper(
    *,
    paper_id: str,
    teacher_id: str,
    student_id: str,
    subject_id: str,
    question_version_id: str,
    answer_version_id: str,
    asset_ids: tuple[str, ...],
    layout_template_id: str,
    review_version_id: str,
) -> Paper | Err:
    """Copy the version ids onto the paper. Empty ids are refused and nothing is stored."""
    if not question_version_id.strip() or not answer_version_id.strip():
        return Err(
            "not_frozen",
            "the question version and the answer version must both be copied",
        )
    return Paper(
        paper_id=paper_id,
        teacher_id=teacher_id,
        student_id=student_id,
        subject_id=subject_id,
        question_version_id=question_version_id,
        answer_version_id=answer_version_id,
        asset_ids=tuple(asset_ids),
        layout_template_id=layout_template_id,
        review_version_id=review_version_id,
        file_id=None,
        status="待渲染",
    )
