"""Admin publication bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class AttachPublicationAssetBody(BaseModel):
    file_id: str = Field(min_length=1)
    kind: Literal["image", "pdf"]
    checksum: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    mime_type: str = Field(min_length=1)


class AttachPublicationAssetResponse(BaseModel):
    result: str
    publication_asset_id: str | None = None


class RemovePublicationAssetResponse(BaseModel):
    result: str


class PublicationAssetItem(BaseModel):
    publication_asset_id: str
    publication_id: str
    file_id: str
    kind: str
    checksum: str
    size_bytes: int
    mime_type: str
    created_at: datetime
    created_by: str


class PublicationAssetListResponse(BaseModel):
    items: list[PublicationAssetItem]
