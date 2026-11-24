"""Vision port. Adapters implement it. This module does not call a network."""

from __future__ import annotations

from typing import Protocol

from backend.ai.domain.records import JudgeAsk, JudgeResult, TranscribeAsk, TranscribeResult


class ModelFault(Exception):
    """A mapped model refusal. The message is the code and nothing else."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class VisionModel(Protocol):
    def transcribe(self, image: bytes, items: tuple[TranscribeAsk, ...]) -> TranscribeResult:
        """Read the handwriting. Do not score it."""

    def judge(self, items: tuple[JudgeAsk, ...]) -> JudgeResult:
        """Suggest a verdict from the stem, the standard answer, and the transcription."""
