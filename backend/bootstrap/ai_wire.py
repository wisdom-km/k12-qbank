"""Choose the vision adapter from the environment. The key is never printed."""

from __future__ import annotations

import os
import sys

_NAMES = ("K12_AI_BASE_URL", "K12_AI_MODEL", "K12_AI_API_KEY")


def build_model() -> object:
    provider = os.environ.get("K12_AI_PROVIDER", "").strip() or "mock"
    if provider == "mock":
        from backend.ai.adapters.mock_model import MockModel

        scenario = os.environ.get("K12_AI_MOCK", "").strip() or "ok"
        return MockModel(scenario=scenario)
    if provider != "volcengine":
        sys.stderr.write("K12_AI_PROVIDER\n")
        raise SystemExit(1)
    missing = [name for name in _NAMES if not os.environ.get(name, "").strip()]
    if missing:
        if os.environ.get("K12_ENV", "").strip() == "production":
            sys.stderr.write("missing " + " ".join(missing) + "\n")
            raise SystemExit(1)
        from backend.ai.adapters.mock_model import UnavailableModel

        return UnavailableModel("ai_provider_incomplete")
    from backend.ai.adapters.volcengine_model import VolcengineModel

    return VolcengineModel(
        base_url=os.environ["K12_AI_BASE_URL"].strip(),
        model=os.environ["K12_AI_MODEL"].strip(),
        api_key=os.environ["K12_AI_API_KEY"].strip(),
        timeout=_timeout(),
    )


def _timeout() -> float:
    raw = os.environ.get("K12_AI_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return 60.0
    try:
        value = float(raw)
    except ValueError:
        return 60.0
    if value <= 0:
        return 60.0
    return value
