"""Load stored runs and decisions, then count. This module does not write."""

from __future__ import annotations

from backend.ai.domain.accuracy import measure
from backend.practice.api import current_review_threshold


def accuracy_report(
    runs: object,
    decisions: object,
    *,
    provider: str = "",
    model: str = "",
) -> dict[str, object]:
    """Read both stores. The cutoff is the same value adopt-confident uses."""
    return measure(
        runs.all_runs(),  # type: ignore[attr-defined]
        decisions.all_current(),  # type: ignore[attr-defined]
        provider=provider,
        model=model,
        current_threshold=current_review_threshold(),
    )
