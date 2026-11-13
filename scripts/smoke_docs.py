"""Repeatable document smoke. This does not test teaching behavior."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "AGENTS.md",
    "PRD.md",
    "ARCHITECTURE.md",
    "RULES.md",
    "DESIGN.md",
    "README.md",
    "CLAUDE.md",
    "docs/WAIVERS.md",
    "docs/adr/0008-logging.md",
    "docs/exec-plans/active/rational-number-loop.md",
    ".env.example",
    ".gitignore",
    "scripts/check.ps1",
    "scripts/check.conf",
    "backend/kernel/logger.py",
)

PHRASES = {
    "AGENTS.md": ("强制项", "长期", "scripts/check.ps1", "任一 MUST"),
    "PRD.md": ("范围外", "US-01", "AC-01"),
    "ARCHITECTURE.md": ("R1", "R6", "request_id", "组合根"),
    "RULES.md": ("L-01", "Definition of Done"),
    "README.md": ("python scripts/status.py", "python scripts/smoke_docs.py"),
}


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        print("SMOKE FAIL: missing " + ", ".join(missing))
        return 1
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if len(agents.splitlines()) > 200:
        print("SMOKE FAIL: AGENTS.md is over 200 lines. Move detail into docs and leave a pointer.")
        return 1
    for name, phrases in PHRASES.items():
        body = (ROOT / name).read_text(encoding="utf-8")
        absent = [phrase for phrase in phrases if phrase not in body]
        if absent:
            print(f"SMOKE FAIL: {name} missing {absent}")
            return 1
    print("SMOKE PASS: required docs and kernel logger port exist. No teaching behavior is tested.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
