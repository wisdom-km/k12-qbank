"""M-04 logging rules. Exit 1 with a fix line. See ARCHITECTURE.md section 运行日志."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "ARCHITECTURE.md"
CORE = ROOT / "backend"

FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(?:logging|structlog|loguru)\b",
    re.M,
)
BARE_PRINT = re.compile(r"(^|[^.\w])print\s*\(")
SECRET_FIELD = re.compile(
    r"(?i)(password|api[_-]?key|access[_-]?token|session|connection[_-]?string|student_name)"
)

REQUIRED_IN_ARCH = (
    "request_id",
    "绝不记",
    "ERROR",
    "WARN",
    "INFO",
    "DEBUG",
    "stdout",
)


def fail(message: str) -> None:
    print(f"M-04 FAIL: {message}")
    print("Fix: follow ARCHITECTURE.md section 运行日志. Core uses the injected Logger port.")
    raise SystemExit(1)


def main() -> int:
    if not ARCH.is_file():
        fail("ARCHITECTURE.md is missing, so the logging decision is not recorded.")
    text = ARCH.read_text(encoding="utf-8")
    missing = [word for word in REQUIRED_IN_ARCH if word not in text]
    if missing:
        fail("ARCHITECTURE.md logging section is missing: " + ", ".join(missing))

    if not CORE.is_dir():
        print("M-04 PASS: logging section present; backend tree absent.")
        return 0

    for path in CORE.rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        in_core = "/domain/" in f"/{rel}/" or "/application/" in f"/{rel}/" or rel.startswith(
            "backend/kernel/"
        )
        if not in_core:
            continue
        if FORBIDDEN_IMPORT.search(body):
            fail(f"{rel} imports a concrete logging library. Inject backend.kernel.Logger instead.")
        if BARE_PRINT.search(body):
            fail(f"{rel} calls print. Use Logger.log with a LogEvent.")
        for index, line in enumerate(body.splitlines(), start=1):
            if "log(" in line and SECRET_FIELD.search(line):
                fail(f"{rel}:{index} looks like a secret or student name in a log call. Remove it.")
    print("M-04 PASS: logging section present; core has no print or logging-library import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
