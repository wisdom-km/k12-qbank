"""Manual check of the Ark endpoint. Tests and CI do not run this script.

Usage:
  python scripts/ai_probe.py
  python scripts/ai_probe.py --image path\\to\\page.jpg
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_NAMES = ("K12_AI_BASE_URL", "K12_AI_MODEL", "K12_AI_API_KEY")
_LABELS = {
    "network": "地址不通",
    "auth_failed": "鉴权失败",
    "model_not_found": "模型 ID 不对",
    "timeout": "超时",
    "model_output_invalid": "输出不合格",
    "ai_provider_incomplete": "未配置",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the configured Ark endpoint.")
    parser.add_argument("--image", default="", help="Optional image to transcribe once.")
    args = parser.parse_args()
    missing = [name for name in _NAMES if not os.environ.get(name, "").strip()]
    if missing:
        print("缺少 " + " ".join(missing))
        return 2
    from backend.bootstrap.ai_wire import build_model

    os.environ["K12_AI_PROVIDER"] = "volcengine"
    model = build_model()
    started = time.perf_counter()
    try:
        raw, prompt_tokens, completion_tokens = model._post("回复 JSON：{\"ok\": true}")
    except Exception as exc:
        code = getattr(exc, "code", "")
        print(_LABELS.get(str(code), "输出不合格"))
        return 1
    elapsed = time.perf_counter() - started
    print("文字请求通过")
    print("耗时秒 " + format(elapsed, ".3f"))
    print("input_tokens " + str(prompt_tokens))
    print("output_tokens " + str(completion_tokens))
    if not isinstance(raw, dict):
        print("输出不合格")
        return 1
    image_path = str(args.image).strip()
    if not image_path:
        return 0
    path = Path(image_path)
    if not path.is_file():
        print("找不到图片")
        return 2
    from backend.ai.domain.records import TranscribeAsk

    started = time.perf_counter()
    try:
        result = model.transcribe(path.read_bytes(), (TranscribeAsk(1, "solution", ()),))
    except Exception as exc:
        code = getattr(exc, "code", "")
        print(_LABELS.get(str(code), "输出不合格"))
        return 1
    elapsed = time.perf_counter() - started
    print("转写耗时秒 " + format(elapsed, ".3f"))
    print("input_tokens " + str(result.input_tokens))
    print("output_tokens " + str(result.output_tokens))
    for item in result.items:
        print(
            json.dumps(
                {
                    "order_no": item.order_no,
                    "transcription": item.transcription,
                    "unreadable": item.unreadable,
                    "confidence": item.confidence,
                },
                ensure_ascii=False,
            )
        )
    print("seen_page_no " + (result.seen_page_no or ""))
    print("seen_external_id_present " + ("yes" if result.seen_external_id else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
