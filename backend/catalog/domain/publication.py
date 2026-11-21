"""One published binding. layout_template_id stays empty in this batch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Publication:
    publication_id: str
    question_version_id: str
    answer_version_id: str
    subject_id: str
    status: str
    layout_template_id: str | None = None
