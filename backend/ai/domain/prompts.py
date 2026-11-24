"""Versioned prompt files. The version string is what a run stores."""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "prompts"
_VERSION = "transcribe-v1/judge-v1"


def prompt_version() -> str:
    for name in ("transcribe-v1.txt", "judge-v1.txt"):
        if not (_DIR / name).is_file():
            raise FileNotFoundError(name)
    return _VERSION


def prompt_text(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")
