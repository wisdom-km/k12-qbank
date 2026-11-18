"""Wire memory adapters. This file does not decide whether a paper may be issued."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from backend.bootstrap.audit_memory import MemoryAudit
from backend.bootstrap.file_log import FileLog
from backend.bootstrap.health import HealthReport, health_report
from backend.bootstrap.stdout_log import StdoutLogger
from backend.catalog.adapters.memory import MemoryApprovals
from backend.kernel.logger import CompositeLogger, Logger
from backend.practice.adapters.files import MemoryFiles
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.application.ports import PageRenderer


@dataclass(frozen=True)
class Loop:
    approvals: MemoryApprovals
    practice: MemoryPractice
    auth: MemoryAuth
    logger: Logger
    files: MemoryFiles
    renderer: PageRenderer
    health: HealthReport


def compose() -> Loop:
    """Wire memory adapters and the fixed health body. No business branch.

    The runtime stream is always stdout. The file sink follows K12_LOG_FILE.
    The audit sink is in memory until a PostgreSQL pool is injected.
    """
    return Loop(
        approvals=MemoryApprovals(),
        practice=MemoryPractice(),
        auth=MemoryAuth(),
        logger=build_logger(),
        files=MemoryFiles(),
        renderer=StdPdf(),
        health=health_report(),
    )


def build_logger(audit: object | None = None) -> Logger:
    stdout = StdoutLogger()
    runtime: list[Logger] = [stdout]
    if os.environ.get("K12_LOG_FILE", "1") != "0":
        directory = Path(os.environ.get("K12_LOG_DIR", "./var/log/k12"))
        retain = _days(os.environ.get("K12_LOG_RETAIN_DAYS"), 14)
        runtime.append(FileLog(directory, retain_days=retain))
    sink = audit if audit is not None else MemoryAudit()
    return CompositeLogger(runtime, sink)  # type: ignore[arg-type]


def _days(raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 1:
        return default
    return value
