"""Count recognition runs against teacher decisions. No I/O."""

from __future__ import annotations

from collections.abc import Sequence

from backend.ai.domain.records import Run, Suggestion

_DECISIVE = frozenset({"correct", "incorrect"})
_SWEEP = (0.5, 0.6, 0.7, 0.8, 0.9)
_SOURCES = ("adopted", "revised", "manual")
_JUDGED = ("local", "model")


def measure(
    runs: Sequence[Run],
    decisions: Sequence[object],
    *,
    provider: str,
    model: str,
    current_threshold: float,
) -> dict[str, object]:
    """Return counts only. Stored text such as a transcription stays out."""
    provider = provider.strip()
    model = model.strip()
    filtering = bool(provider or model)
    chosen = [
        run
        for run in runs
        if (not provider or run.provider == provider) and (not model or run.model == model)
    ]
    chosen_ids = {run.run_id for run in chosen}
    suggestions = _index(chosen)
    linked: list[tuple[object, Suggestion]] = []
    unlinked = 0
    sources = {name: 0 for name in _SOURCES}
    for decision in decisions:
        if _text(decision, "voided_at"):
            continue
        if not _in_scope(decision, chosen_ids, filtering):
            continue
        key = (
            _text(decision, "ai_run_id"),
            _text(decision, "paper_id"),
            int(getattr(decision, "order_no")),
        )
        suggestion = suggestions.get(key)
        if suggestion is None:
            unlinked += 1
            continue
        linked.append((decision, suggestion))
        source = _text(decision, "source")
        if source in sources:
            sources[source] += 1
    judged = {name: _empty_judged() for name in _JUDGED}
    decisive = agreed = disagreed = unsure = 0
    for decision, suggestion in linked:
        unsure_row = _unsure(suggestion)
        decisive_row = _decisive(suggestion)
        same = suggestion.verdict == _text(decision, "verdict")
        if unsure_row:
            unsure += 1
        if decisive_row:
            decisive += 1
            if same:
                agreed += 1
            else:
                disagreed += 1
        bucket = judged.get(suggestion.judged_by)
        if bucket is None:
            continue
        bucket["total"] = int(bucket["total"]) + 1
        if unsure_row:
            bucket["unsure_or_unreadable"] = int(bucket["unsure_or_unreadable"]) + 1
        if decisive_row:
            bucket["decisive"] = int(bucket["decisive"]) + 1
            if same:
                bucket["agreed"] = int(bucket["agreed"]) + 1
            else:
                bucket["disagreed"] = int(bucket["disagreed"]) + 1
    for bucket in judged.values():
        bucket["agreement_rate"] = _rate(int(bucket["agreed"]), int(bucket["decisive"]))
    return {
        "current_threshold": current_threshold,
        "available_models": _models(runs),
        "runs": _runs(chosen),
        "items": {
            "decided_total": len(linked) + unlinked,
            "linked_ai": len(linked),
            "unlinked_manual": unlinked,
            "by_source": sources,
            "ai_decisive": decisive,
            "ai_unsure_or_unreadable": unsure,
            "agreed": agreed,
            "disagreed": disagreed,
            "agreement_rate": _rate(agreed, decisive),
            "by_judged_by": judged,
        },
        "thresholds": [
            _threshold_row(linked, value)
            for value in _levels(current_threshold)
        ],
    }


def _index(runs: Sequence[Run]) -> dict[tuple[str, str, int], Suggestion]:
    found: dict[tuple[str, str, int], Suggestion] = {}
    for run in runs:
        for item in run.suggestions:
            found[(run.run_id, item.paper_id, item.order_no)] = item
    return found


def _in_scope(decision: object, chosen_ids: set[str], filtering: bool) -> bool:
    run_id = _text(decision, "ai_run_id")
    if not filtering or not run_id:
        return True
    return run_id in chosen_ids


def _models(runs: Sequence[Run]) -> list[dict[str, str]]:
    pairs = sorted({(run.provider, run.model) for run in runs})
    return [{"provider": provider, "model": model} for provider, model in pairs]


def _runs(runs: Sequence[Run]) -> dict[str, object]:
    failed: dict[str, int] = {}
    input_tokens = 0
    output_tokens = 0
    for run in runs:
        if run.status == "failed":
            failed[run.error_code] = failed.get(run.error_code, 0) + 1
        if run.status in {"succeeded", "failed"}:
            input_tokens += run.input_tokens or 0
            output_tokens += run.output_tokens or 0
    return {
        "total": len(runs),
        "succeeded": sum(1 for run in runs if run.status == "succeeded"),
        "failed": sum(1 for run in runs if run.status == "failed"),
        "active": sum(1 for run in runs if run.status in {"queued", "running"}),
        "failed_by_code": dict(sorted(failed.items())),
        "external_match": _matches(runs, "external_match"),
        "page_match": _matches(runs, "page_match"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _matches(runs: Sequence[Run], field: str) -> dict[str, int]:
    counts = {"matched": 0, "mismatched": 0, "missing": 0}
    for run in runs:
        if run.status != "succeeded":
            continue
        counts[_bucket(str(getattr(run, field)))] += 1
    return counts


def _bucket(value: str) -> str:
    if value == "consistent":
        return "matched"
    if value == "mismatch":
        return "mismatched"
    return "missing"


def _threshold_row(linked: Sequence[tuple[object, Suggestion]], threshold: float) -> dict[str, object]:
    confident = agreed = false_confident = 0
    for decision, suggestion in linked:
        if not _confident(suggestion, threshold):
            continue
        confident += 1
        if suggestion.verdict == _text(decision, "verdict"):
            agreed += 1
        else:
            false_confident += 1
    return {
        "threshold": threshold,
        "confident_count": confident,
        "confident_agreed": agreed,
        "false_confident": false_confident,
        "review_needed_count": len(linked) - confident,
        "confident_accuracy": _rate(agreed, confident),
        "coverage_rate": _rate(confident, len(linked)),
    }


def _levels(current: float) -> list[float]:
    values = list(_SWEEP)
    if not any(abs(item - current) < 1e-9 for item in values):
        values.append(current)
    values.sort()
    return values


def _decisive(suggestion: Suggestion) -> bool:
    return (not suggestion.unreadable) and suggestion.verdict in _DECISIVE


def _unsure(suggestion: Suggestion) -> bool:
    return suggestion.unreadable or suggestion.verdict == "unsure"


def _confident(suggestion: Suggestion, threshold: float) -> bool:
    return _decisive(suggestion) and suggestion.confidence >= threshold


def _empty_judged() -> dict[str, object]:
    return {
        "total": 0,
        "decisive": 0,
        "agreed": 0,
        "disagreed": 0,
        "unsure_or_unreadable": 0,
        "agreement_rate": None,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _text(row: object, name: str) -> str:
    return str(getattr(row, name) or "")
