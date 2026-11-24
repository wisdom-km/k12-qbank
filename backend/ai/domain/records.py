"""Plain records for one recognition run. No I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoxRel:
    """One answer box as fractions of the page. Origin is the top left."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class TranscribeAsk:
    """What the transcribe step may send. No stem and no standard answer."""

    order_no: int
    question_type: str
    boxes: tuple[BoxRel, ...]


@dataclass(frozen=True)
class Transcribed:
    order_no: int
    transcription: str
    unreadable: bool
    confidence: float


@dataclass(frozen=True)
class TranscribeResult:
    items: tuple[Transcribed, ...]
    seen_external_id: str | None
    seen_page_no: str | None
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class JudgeAsk:
    """What the judge step may send. No photo."""

    order_no: int
    question_type: str
    stem: str
    standard_answer: str
    transcription: str


@dataclass(frozen=True)
class Judged:
    order_no: int
    verdict: str
    reason: str


@dataclass(frozen=True)
class JudgeResult:
    items: tuple[Judged, ...]
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class WorkItem:
    """One frozen question on this page. The model does not receive this whole object."""

    order_no: int
    question_type: str
    stem: str
    standard_answer: str
    boxes: tuple[tuple[float, float, float, float], ...]
    blank_count: int


@dataclass(frozen=True)
class Context:
    """In-memory job. paper_id and the expected number stay here and are not sent onward."""

    run_id: str
    intake_id: str
    paper_id: str
    page_no: int
    image: bytes
    items: tuple[WorkItem, ...]
    expected_external_id: str
    provider: str
    model_name: str
    prompt_version: str


@dataclass(frozen=True)
class Suggestion:
    run_id: str
    paper_id: str
    order_no: int
    transcription: str
    unreadable: bool
    confidence: float
    verdict: str
    reason: str
    judged_by: str


@dataclass(frozen=True)
class Run:
    run_id: str
    intake_id: str
    provider: str
    model: str
    prompt_version: str
    status: str
    error_code: str = ""
    started_at: str = ""
    finished_at: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    external_match: str = ""
    page_match: str = ""
    suggestions: tuple[Suggestion, ...] = ()
