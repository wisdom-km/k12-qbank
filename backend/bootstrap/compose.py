"""Wire memory adapters. This file does not decide whether a paper may be issued."""

from __future__ import annotations

from dataclasses import dataclass

from backend.bootstrap.health import HealthReport, health_report
from backend.bootstrap.stdout_log import StdoutLogger
from backend.catalog.adapters.memory import MemoryApprovals
from backend.kernel.logger import Logger
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

    PostgreSQL is not connected. The in-memory lock remains the confirm contract.
    """
    return Loop(
        approvals=MemoryApprovals(),
        practice=MemoryPractice(),
        auth=MemoryAuth(),
        logger=StdoutLogger(),
        files=MemoryFiles(),
        renderer=StdPdf(),
        health=health_report(),
    )
