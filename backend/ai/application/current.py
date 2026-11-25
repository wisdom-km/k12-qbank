"""Load the suggestion a teacher may confirm. This module does not adopt it."""

from __future__ import annotations

from backend.ai.domain.current import PageStamp, select_recognition
from backend.ai.domain.records import Run


def recognition_of(stores: object, paper_id: str) -> dict[str, object]:
    """Plain facts for one paper. Practice does not import this slice's domain."""
    intake = getattr(stores, "intake")
    runs_store = getattr(stores, "ai_runs")
    history = getattr(intake, "history", None)
    pages = () if history is None else history(paper_id)
    stamps = tuple(
        PageStamp(page.intake_id, int(page.page_no), page.superseded_at is not None) for page in pages
    )
    runs: list[Run] = []
    listing = getattr(runs_store, "for_intake", None)
    if listing is not None:
        for page in pages:
            runs.extend(listing(page.intake_id))
    return select_recognition(stamps, tuple(runs))
