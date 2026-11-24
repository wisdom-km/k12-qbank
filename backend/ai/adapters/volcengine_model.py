"""Volcengine Ark chat completions. httpx stays in this adapter."""

from __future__ import annotations

import base64
import json

import httpx

from backend.ai.domain.model import ModelFault
from backend.ai.domain.payload import parse_judge, parse_transcribe
from backend.ai.domain.prompts import prompt_text
from backend.ai.domain.records import (
    JudgeAsk,
    JudgeResult,
    TranscribeAsk,
    TranscribeResult,
)


class VolcengineModel:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: float) -> None:
        self._url = _endpoint(base_url)
        self._model = model
        self._key = api_key
        self._timeout = timeout

    def transcribe(self, image: bytes, items: tuple[TranscribeAsk, ...]) -> TranscribeResult:
        from backend.ai.domain.payload import transcribe_document

        text = prompt_text("transcribe-v1.txt").rstrip() + "\n" + json.dumps(
            transcribe_document(items),
            ensure_ascii=False,
        )
        content = [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": _data_url(image)}},
        ]
        raw, prompt_tokens, completion_tokens = self._post(content)
        parsed = parse_transcribe(raw, tuple(item.order_no for item in items))
        return TranscribeResult(
            items=parsed.items,
            seen_external_id=parsed.seen_external_id,
            seen_page_no=parsed.seen_page_no,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

    def judge(self, items: tuple[JudgeAsk, ...]) -> JudgeResult:
        from backend.ai.domain.payload import judge_document

        text = prompt_text("judge-v1.txt").rstrip() + "\n" + json.dumps(
            judge_document(items),
            ensure_ascii=False,
        )
        raw, prompt_tokens, completion_tokens = self._post(text)
        parsed = parse_judge(raw, tuple(item.order_no for item in items))
        return JudgeResult(
            items=parsed.items,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

    def _post(self, content: object) -> tuple[object, int, int]:
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                self._url,
                json=body,
                headers={"Authorization": "Bearer " + self._key},
                timeout=self._timeout,
                trust_env=False,
            )
        except httpx.TimeoutException:
            raise ModelFault("timeout") from None
        except httpx.TransportError:
            raise ModelFault("network") from None
        if response.status_code in {401, 403}:
            raise ModelFault("auth_failed") from None
        if response.status_code == 404:
            raise ModelFault("model_not_found") from None
        if response.status_code >= 400:
            raise ModelFault("network") from None
        try:
            payload = response.json()
        except Exception:
            raise ModelFault("model_output_invalid") from None
        message = _message(payload)
        try:
            parsed = json.loads(message)
        except Exception:
            raise ModelFault("model_output_invalid") from None
        usage = payload.get("usage") if isinstance(payload, dict) else None
        return parsed, _tokens(usage, "prompt_tokens"), _tokens(usage, "completion_tokens")


def _endpoint(base_url: str) -> str:
    text = base_url.strip().rstrip("/")
    if text.endswith("/chat/completions"):
        return text
    return text + "/chat/completions"


def _data_url(image: bytes) -> str:
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        media = "image/png"
    else:
        media = "image/jpeg"
    encoded = base64.b64encode(image).decode("ascii")
    return "data:" + media + ";base64," + encoded


def _message(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ModelFault("model_output_invalid")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelFault("model_output_invalid")
    first = choices[0]
    if not isinstance(first, dict):
        raise ModelFault("model_output_invalid")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ModelFault("model_output_invalid")
    content = message.get("content")
    if not isinstance(content, str):
        raise ModelFault("model_output_invalid")
    return content


def _tokens(usage: object, name: str) -> int:
    if not isinstance(usage, dict):
        return 0
    value = usage.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
