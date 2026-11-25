"""Which succeeded run is the suggestion a teacher may confirm. No I/O."""

from __future__ import annotations

from dataclasses import dataclass

from backend.ai.domain.records import Run


@dataclass(frozen=True)
class PageStamp:
    """One intake row reduced to what the current-suggestion rule needs."""

    intake_id: str
    page_no: int
    superseded: bool


def select_recognition(pages: tuple[PageStamp, ...], runs: tuple[Run, ...]) -> dict[str, object]:
    """Live photos use their latest success. Replaced photos are not current."""
    live = {page.intake_id: page for page in pages if not page.superseded}
    dead = {page.intake_id for page in pages if page.superseded}
    latest = {intake_id: _latest_success(runs, intake_id) for intake_id in live}
    suggestions: list[dict[str, object]] = []
    covered: set[int] = set()
    for intake_id, run in latest.items():
        if run is None:
            continue
        for item in run.suggestions:
            covered.add(item.order_no)
            suggestions.append(
                {
                    "order_no": item.order_no,
                    "run_id": run.run_id,
                    "transcription": item.transcription,
                    "confidence": item.confidence,
                    "verdict": item.verdict,
                    "reason": item.reason,
                    "judged_by": item.judged_by,
                    "unreadable": item.unreadable,
                }
            )
    stale: set[int] = set()
    for run in runs:
        if run.status != "succeeded" or run.intake_id not in dead:
            continue
        for item in run.suggestions:
            if item.order_no not in covered:
                stale.add(item.order_no)
    mismatch: list[int] = []
    for intake_id, page in live.items():
        run = latest.get(intake_id)
        if run is None:
            continue
        if run.external_match == "mismatch" or run.page_match == "mismatch":
            mismatch.append(page.page_no)
    return {
        "suggestions": suggestions,
        "stale_orders": sorted(stale),
        "mismatch_pages": sorted(set(mismatch)),
        "received_pages": sorted({page.page_no for page in live.values()}),
    }


def _latest_success(runs: tuple[Run, ...], intake_id: str) -> Run | None:
    found = [run for run in runs if run.intake_id == intake_id and run.status == "succeeded"]
    if not found:
        return None
    found.sort(key=lambda run: (run.finished_at, run.started_at, run.run_id))
    return found[-1]
