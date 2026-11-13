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
    r"(?i)(?<![A-Za-z0-9])("
    r"password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|cookie|session|connection[_-]?string|"
    r"student[_-]?(?:name|id|no)|photo|request[_-]?body|prompt|card[_-]?number|"
    r"学号|姓名"
    r")(?![A-Za-z0-9])"
)
LOG_CALL = re.compile(r"(?<!def )(?<!\w)log\s*\(")
FORMATTED = re.compile(r"""f["']|\.format\s*\(""")

REQUIRED_IN_ARCH = (
    "request_id",
    "绝不记",
    "ERROR",
    "WARN",
    "INFO",
    "DEBUG",
    "stdout",
)


def fail(code: str, message: str, fix: str) -> None:
    print(f"M-04 FAIL: {code}: {message}")
    print(f"Fix: {fix}")
    raise SystemExit(1)


def main() -> int:
    if not ARCH.is_file():
        fail(
            "L-03",
            "ARCHITECTURE.md is missing, so the logging decision is not recorded.",
            "Restore ARCHITECTURE.md section 运行日志.",
        )
    text = ARCH.read_text(encoding="utf-8")
    missing = [word for word in REQUIRED_IN_ARCH if word not in text]
    if missing:
        fail(
            "L-03",
            "ARCHITECTURE.md logging section is missing: " + ", ".join(missing),
            "Put the missing words back in ARCHITECTURE.md section 运行日志.",
        )

    if not CORE.is_dir():
        print("M-04 PASS: logging section present; backend tree absent.")
        return 0

    for path in CORE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        body = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        in_core = "/domain/" in f"/{rel}/" or "/application/" in f"/{rel}/" or rel.startswith(
            "backend/kernel/"
        )
        if in_core and FORBIDDEN_IMPORT.search(body):
            fail(
                "L-03",
                f"{rel} imports a concrete logging library.",
                "Inject backend.kernel.Logger. Do not import logging, structlog, or loguru. "
                "See ARCHITECTURE.md 运行日志.",
            )
        if in_core and BARE_PRINT.search(body):
            fail(
                "L-03",
                f"{rel} calls print.",
                "Use Logger.log with a LogEvent. See ARCHITECTURE.md 运行日志 and RULES L-03.",
            )
        for index, line in enumerate(body.splitlines(), start=1):
            if not LOG_CALL.search(line):
                continue
            if SECRET_FIELD.search(line):
                fail(
                    "L-05",
                    f"{rel}:{index} looks like a secret or student field in a log call.",
                    "Remove that field. Do not log passwords, tokens, session, names, or student ids. "
                    "See ARCHITECTURE.md 绝不记 and RULES L-05.",
                )
            if FORMATTED.search(line):
                fail(
                    "L-05",
                    f"{rel}:{index} builds a log line with an f-string or format call.",
                    "Pass a LogEvent with fixed field names. Do not concatenate the message. "
                    "See ARCHITECTURE.md 运行日志.",
                )
    print("M-04 PASS: logging section present; core has no print or logging-library import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
