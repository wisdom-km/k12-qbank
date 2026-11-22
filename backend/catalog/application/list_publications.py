"""List publication rows. This read does not write an audit event."""

from __future__ import annotations

from typing import Literal

from backend.catalog.api import Publications
from backend.catalog.domain.publication import Publication, bound_page

__all__ = ["bound_page", "list_publications"]


def list_publications(
    publications: Publications,
    question_version_id: str | None = None,
    answer_version_id: str | None = None,
    subject_id: str | None = None,
    status: Literal["active", "retired"] | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[tuple[Publication, ...], int]:
    """Return one page and the filtered total. The caller clamps the page. The port does not see a role."""
    return publications.list_page(
        question_version_id,
        answer_version_id,
        subject_id,
        status,
        offset,
        limit,
    )
