"""Admin accuracy report. Counts only. No student text."""

from __future__ import annotations

from pydantic import BaseModel


class MatchCounts(BaseModel):
    matched: int
    mismatched: int
    missing: int


class RunOverview(BaseModel):
    total: int
    succeeded: int
    failed: int
    active: int
    failed_by_code: dict[str, int]
    external_match: MatchCounts
    page_match: MatchCounts
    input_tokens: int
    output_tokens: int


class SourceCounts(BaseModel):
    adopted: int
    revised: int
    manual: int


class JudgeCounts(BaseModel):
    total: int
    decisive: int
    agreed: int
    disagreed: int
    unsure_or_unreadable: int
    agreement_rate: float | None


class ItemOverview(BaseModel):
    decided_total: int
    linked_ai: int
    unlinked_manual: int
    by_source: SourceCounts
    ai_decisive: int
    ai_unsure_or_unreadable: int
    agreed: int
    disagreed: int
    agreement_rate: float | None
    by_judged_by: dict[str, JudgeCounts]


class ThresholdRow(BaseModel):
    threshold: float
    confident_count: int
    confident_agreed: int
    false_confident: int
    review_needed_count: int
    confident_accuracy: float | None
    coverage_rate: float | None


class ModelName(BaseModel):
    provider: str
    model: str


class AccuracyResponse(BaseModel):
    current_threshold: float
    available_models: list[ModelName]
    runs: RunOverview
    items: ItemOverview
    thresholds: list[ThresholdRow]
