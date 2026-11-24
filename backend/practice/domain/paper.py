"""R2: an issued paper keeps the version and asset ids from issue time."""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend.kernel.result import Err


@dataclass(frozen=True)
class Paper:
    """question_version_id, answer_version_id, and formula are the frozen issue-time copy."""

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
    item_order: tuple[str, ...] = ()
    file_checksum: str | None = None
    formula: str = ""
    qr_printed: bool = False
    printed_external_id: str = ""
    slots_per_page: int = 1
    layout_kind: str = "slots"
    layout_params: str = ""
    issued_on: str = ""


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
    item_order: tuple[str, ...] = (),
    formula: str = "",
    qr_printed: bool = False,
    printed_external_id: str = "",
    slots_per_page: int = 1,
    layout_kind: str = "slots",
    layout_params: str = "",
    issued_on: str = "",
) -> Paper | Err:
    """Copy the version ids and the formula onto the paper. Empty ids are refused."""
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
        item_order=tuple(item_order),
        file_checksum=None,
        formula=formula,
        qr_printed=qr_printed,
        printed_external_id=printed_external_id,
        slots_per_page=slots_per_page,
        layout_kind=layout_kind,
        layout_params=layout_params,
        issued_on=issued_on,
    )


def mark_printable(paper: Paper, *, file_id: str, checksum: str) -> Paper | Err:
    """A paper becomes printable only after a file id and checksum are stored.

    The bytes themselves stay in the file store. This function only records the id.
    """
    if paper.status != "待渲染":
        return Err("not_rendering", "only a paper waiting for render can become printable")
    if not file_id.strip() or not checksum.strip():
        return Err("not_rendered", "a printable paper needs a file id and a checksum")
    return replace(paper, file_id=file_id, file_checksum=checksum, status="可打印")


def mark_issued(paper: Paper, *, publication_retired: bool) -> Paper | Err:
    """Hand-out checks retirement again. A retired publication is not issued."""
    if publication_retired:
        return Err("retired", "the publication was retired before the paper was handed out")
    if paper.status != "可打印" or not paper.file_id or not paper.file_checksum:
        return Err("not_printable", "only a printable paper with a stored file can be handed out")
    return replace(paper, status="已发放")


def recall_file(paper: Paper, *, file_id: str, checksum: str) -> Err | None:
    """The old PDF is the stored file id. A changed checksum fails and the id stays."""
    if not paper.file_id or not paper.file_checksum:
        return Err("not_rendered", "this paper has no stored file")
    if file_id != paper.file_id or checksum != paper.file_checksum:
        return Err("file_changed", "the stored file id stays")
    return None
