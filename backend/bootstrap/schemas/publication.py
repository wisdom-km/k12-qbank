"""Admin publication list bodies."""

from __future__ import annotations

from pydantic import BaseModel


class PublicationItem(BaseModel):
    publication_id: str
    question_version_id: str
    answer_version_id: str
    subject_id: str
    status: str
    layout_template_id: str | None = None


class PublicationListResponse(BaseModel):
    items: list[PublicationItem]
    total: int
    offset: int
    limit: int
