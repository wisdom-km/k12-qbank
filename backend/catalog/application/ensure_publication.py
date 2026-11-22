"""Write the grandfather row when both sides are already approved.

This is not a publish action. It does not choose a layout and it does not write publication_asset.
"""

from __future__ import annotations

from typing import Literal

from backend.catalog.api import Publications
from backend.catalog.domain.publication import Publication

Outcome = Literal["created", "already_active", "retired_present"]


def ensure_publication_on_both_approved(
    publications: Publications,
    q_vid: str,
    a_vid: str,
    subject_id: str,
) -> Outcome:
    """Create one active row, or leave an existing active or retired row untouched."""
    rows = publications.rows_for(q_vid, a_vid)
    if any(row.status == "active" for row in rows):
        return "already_active"
    if any(row.status == "retired" for row in rows):
        return "retired_present"
    publications.put(
        Publication(
            publication_id="pub-" + q_vid + "-" + a_vid,
            question_version_id=q_vid,
            answer_version_id=a_vid,
            subject_id=subject_id,
            status="active",
        )
    )
    return "created"
