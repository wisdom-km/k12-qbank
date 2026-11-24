"""Deterministic stand-in. Tests and development use this. It stores asks, not image bytes."""

from __future__ import annotations

import threading

from backend.ai.domain.model import ModelFault
from backend.ai.domain.records import (
    JudgeAsk,
    Judged,
    JudgeResult,
    TranscribeAsk,
    Transcribed,
    TranscribeResult,
)


class MockModel:
    def __init__(
        self,
        scenario: str = "ok",
        transcription: str = "2",
        confidence: float = 0.91,
        unreadable: bool = False,
        seen_external_id: str | None = None,
        seen_page_no: str | None = None,
        verdict: str = "correct",
        reason: str = "与标准答案一致",
    ) -> None:
        self.scenario = scenario
        self.transcription = transcription
        self.confidence = confidence
        self.unreadable = unreadable
        self.seen_external_id = seen_external_id
        self.seen_page_no = seen_page_no
        self.verdict = verdict
        self.reason = reason
        self.transcribe_asks: list[tuple[TranscribeAsk, ...]] = []
        self.judge_asks: list[tuple[JudgeAsk, ...]] = []
        self.image_lengths: list[int] = []
        self.entered = threading.Event()
        self.hold = threading.Event()

    def transcribe(self, image: bytes, items: tuple[TranscribeAsk, ...]) -> TranscribeResult:
        self.transcribe_asks.append(items)
        self.image_lengths.append(len(image))
        if self.scenario == "hold":
            self.entered.set()
            self.hold.wait(timeout=8)
        if self.scenario == "timeout":
            raise ModelFault("timeout")
        if self.scenario == "auth":
            raise ModelFault("auth_failed")
        if self.scenario == "invalid":
            raise ModelFault("model_output_invalid")
        unreadable = self.unreadable or self.scenario == "unreadable"
        text = "" if unreadable else self.transcription
        confidence = 0.2 if unreadable else self.confidence
        return TranscribeResult(
            items=tuple(
                Transcribed(
                    order_no=item.order_no,
                    transcription=text,
                    unreadable=unreadable,
                    confidence=confidence,
                )
                for item in items
            ),
            seen_external_id=self.seen_external_id,
            seen_page_no=self.seen_page_no,
            input_tokens=4,
            output_tokens=2,
        )

    def judge(self, items: tuple[JudgeAsk, ...]) -> JudgeResult:
        self.judge_asks.append(items)
        if self.scenario == "invalid_judge":
            raise ModelFault("model_output_invalid")
        if self.scenario == "timeout":
            raise ModelFault("timeout")
        if self.scenario == "auth":
            raise ModelFault("auth_failed")
        return JudgeResult(
            items=tuple(
                Judged(order_no=item.order_no, verdict=self.verdict, reason=self.reason)
                for item in items
            ),
            input_tokens=4,
            output_tokens=2,
        )


class UnavailableModel:
    """Selected provider cannot be built. The code is fixed. No configuration value is kept."""

    def __init__(self, code: str) -> None:
        self._code = code

    def transcribe(self, image: bytes, items: tuple[TranscribeAsk, ...]) -> TranscribeResult:
        raise ModelFault(self._code)

    def judge(self, items: tuple[JudgeAsk, ...]) -> JudgeResult:
        raise ModelFault(self._code)
