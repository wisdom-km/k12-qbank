"""Redacted request bodies and strict response checks."""

from __future__ import annotations

from backend.ai.domain.model import ModelFault
from backend.ai.domain.records import (
    BoxRel,
    JudgeAsk,
    Judged,
    JudgeResult,
    TranscribeAsk,
    Transcribed,
    TranscribeResult,
)

PAGE_W = 595.0
PAGE_H = 842.0
_VERDICTS = frozenset({"correct", "incorrect", "partial", "unsure"})
_TRANSCRIBE_ITEM = frozenset({"order_no", "transcription", "unreadable", "confidence"})
_JUDGE_ITEM = frozenset({"order_no", "verdict", "reason"})


def relative_box(x: float, y: float, w: float, h: float) -> BoxRel:
    """PDF points, origin bottom left, become fractions of the page from the top left."""
    return BoxRel(
        x=_unit(x / PAGE_W),
        y=_unit((PAGE_H - (y + h)) / PAGE_H),
        w=_unit(w / PAGE_W),
        h=_unit(h / PAGE_H),
    )


def transcribe_document(items: tuple[TranscribeAsk, ...]) -> dict[str, object]:
    return {
        "items": [
            {
                "order_no": item.order_no,
                "question_type": item.question_type,
                "boxes": [
                    {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
                    for box in item.boxes
                ],
            }
            for item in items
        ]
    }


def judge_document(items: tuple[JudgeAsk, ...]) -> dict[str, object]:
    return {
        "items": [
            {
                "order_no": item.order_no,
                "question_type": item.question_type,
                "stem": item.stem,
                "standard_answer": item.standard_answer,
                "transcription": item.transcription,
            }
            for item in items
        ]
    }


def parse_transcribe(payload: object, order_nos: tuple[int, ...]) -> TranscribeResult:
    if not isinstance(payload, dict):
        raise ModelFault("model_output_invalid")
    allowed = {"seen_external_id", "seen_page_no", "items"}
    if not set(payload).issubset(allowed) or "items" not in payload:
        raise ModelFault("model_output_invalid")
    rows = _rows(payload.get("items"), _TRANSCRIBE_ITEM, order_nos)
    items: list[Transcribed] = []
    for row in rows:
        confidence = row.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ModelFault("model_output_invalid")
        if confidence < 0 or confidence > 1:
            raise ModelFault("model_output_invalid")
        unreadable = row.get("unreadable")
        transcription = row.get("transcription")
        if not isinstance(unreadable, bool) or not isinstance(transcription, str):
            raise ModelFault("model_output_invalid")
        items.append(
            Transcribed(
                order_no=_order(row.get("order_no")),
                transcription=transcription,
                unreadable=unreadable,
                confidence=float(confidence),
            )
        )
    return TranscribeResult(
        items=tuple(items),
        seen_external_id=_seen_text(payload.get("seen_external_id", None)),
        seen_page_no=_seen_page(payload.get("seen_page_no", None)),
        input_tokens=0,
        output_tokens=0,
    )


def parse_judge(payload: object, order_nos: tuple[int, ...]) -> JudgeResult:
    if not isinstance(payload, dict) or set(payload) != {"items"}:
        raise ModelFault("model_output_invalid")
    rows = _rows(payload.get("items"), _JUDGE_ITEM, order_nos)
    items: list[Judged] = []
    for row in rows:
        verdict = row.get("verdict")
        reason = row.get("reason")
        if verdict not in _VERDICTS or not isinstance(reason, str) or not reason.strip():
            raise ModelFault("model_output_invalid")
        items.append(Judged(order_no=_order(row.get("order_no")), verdict=str(verdict), reason=reason))
    return JudgeResult(items=tuple(items), input_tokens=0, output_tokens=0)


def match_external(expected: str, seen: str | None) -> str:
    if seen is None or not seen.strip():
        return "unread"
    if expected.strip() and expected.strip() == seen.strip():
        return "consistent"
    return "mismatch"


def match_page(page_no: int, seen: str | None) -> str:
    if seen is None or not seen.strip():
        return "unread"
    if seen.strip() == str(page_no):
        return "consistent"
    return "mismatch"


def _rows(value: object, fields: frozenset[str], order_nos: tuple[int, ...]) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ModelFault("model_output_invalid")
    rows: list[dict[str, object]] = []
    seen: list[int] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != fields:
            raise ModelFault("model_output_invalid")
        number = _order(item.get("order_no"))
        seen.append(number)
        rows.append(item)
    if sorted(seen) != sorted(order_nos) or len(seen) != len(set(seen)):
        raise ModelFault("model_output_invalid")
    return rows


def _order(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelFault("model_output_invalid")
    return value


def _seen_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ModelFault("model_output_invalid")
    return value


def _seen_page(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ModelFault("model_output_invalid")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise ModelFault("model_output_invalid")


def _unit(value: float) -> float:
    return round(value, 6)
