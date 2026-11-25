"""One teacher conclusion for one paper item. AI text stays outside this module."""

from __future__ import annotations

from dataclasses import dataclass

from backend.kernel.result import Err

VERDICTS = frozenset({"correct", "incorrect", "partial", "blank"})
ACTIONS = frozenset({"adopt", "revise", "manual"})
SOURCES = frozenset({"adopted", "revised", "manual"})


@dataclass(frozen=True)
class SuggestionFact:
    """The current suggestion the teacher may adopt or revise. No photo bytes."""

    run_id: str
    order_no: int
    transcription: str
    confidence: float
    verdict: str
    reason: str
    judged_by: str
    unreadable: bool


@dataclass(frozen=True)
class TeacherDecision:
    """One stored conclusion. voided_at empty means this row is the current one."""

    decision_id: str
    paper_id: str
    order_no: int
    verdict: str
    source: str
    decided_by: str
    decided_at: str
    ai_run_id: str = ""
    ai_verdict: str = ""
    ai_confidence: float | None = None
    corrected_transcription: str = ""
    comment: str = ""
    voided_at: str = ""


@dataclass(frozen=True)
class PlannedDecision:
    """What to store. adopted and revised keep the AI verdict from this moment."""

    source: str
    verdict: str
    ai_run_id: str
    ai_verdict: str
    ai_confidence: float | None
    corrected_transcription: str
    comment: str
    agrees: bool


def review_threshold(raw: str) -> float:
    """Empty or unusable values stay at 0.6. The caller reads the environment."""
    text = raw.strip()
    if not text:
        return 0.6
    try:
        value = float(text)
    except ValueError:
        return 0.6
    if value < 0 or value > 1:
        return 0.6
    return value


def needs_review(confidence: float, unreadable: bool, threshold: float) -> bool:
    """Below the threshold, or unreadable. Equal to the threshold does not."""
    return unreadable or confidence < threshold


def confident_local(fact: SuggestionFact, threshold: float) -> bool:
    """A bulk adopt may take this row. The teacher still has to confirm the call."""
    return (
        fact.judged_by == "local"
        and fact.confidence >= threshold
        and fact.verdict != "unsure"
        and fact.verdict in VERDICTS
    )


def plan_decision(
    action: str,
    verdict: str,
    fact: SuggestionFact | None,
    *,
    stale: bool,
    corrected_transcription: str,
    comment: str,
) -> PlannedDecision | Err:
    """Pick the one conclusion. A missing suggestion cannot be adopted or revised."""
    if action not in ACTIONS:
        return Err("invalid_action", "the action must be adopt, revise, or manual")
    note = comment.strip()
    transcript = corrected_transcription.strip()
    if len(note) > 2000 or len(transcript) > 2000:
        return Err("note_too_long", "the note is too long")
    if fact is None:
        if action != "manual":
            if stale:
                return Err("suggestion_stale", "the photo was replaced; recognize it again or grade by hand")
            return Err("suggestion_required", "there is no suggestion; grade this item by hand")
        if verdict not in VERDICTS:
            return Err("invalid_verdict", "the verdict must be correct, incorrect, partial, or blank")
        return PlannedDecision("manual", verdict, "", "", None, transcript, note, False)
    if action == "manual":
        if verdict not in VERDICTS:
            return Err("invalid_verdict", "the verdict must be correct, incorrect, partial, or blank")
        return PlannedDecision("manual", verdict, "", "", None, transcript, note, False)
    if action == "adopt":
        if fact.verdict == "unsure":
            return Err("cannot_adopt_unsure", "an unsure suggestion cannot be adopted")
        if fact.verdict not in VERDICTS:
            return Err("invalid_verdict", "the suggestion verdict cannot be stored")
        return PlannedDecision(
            "adopted",
            fact.verdict,
            fact.run_id,
            fact.verdict,
            fact.confidence,
            transcript,
            note,
            True,
        )
    if verdict not in VERDICTS:
        return Err("invalid_verdict", "the verdict must be correct, incorrect, partial, or blank")
    return PlannedDecision(
        "revised",
        verdict,
        fact.run_id,
        fact.verdict,
        fact.confidence,
        transcript,
        note,
        verdict == fact.verdict,
    )


def same_decision(
    *,
    source: str,
    verdict: str,
    ai_run_id: str,
    ai_verdict: str,
    ai_confidence: float | None,
    corrected_transcription: str,
    comment: str,
    planned: PlannedDecision,
) -> bool:
    """A repeated click keeps the current row."""
    return (
        source == planned.source
        and verdict == planned.verdict
        and ai_run_id == planned.ai_run_id
        and ai_verdict == planned.ai_verdict
        and ai_confidence == planned.ai_confidence
        and corrected_transcription == planned.corrected_transcription
        and comment == planned.comment
    )
