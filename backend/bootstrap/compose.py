"""Wire memory adapters. This file does not decide whether a paper may be issued."""

from __future__ import annotations

from dataclasses import dataclass

from backend.bootstrap.stdout_log import StdoutLogger
from backend.catalog.adapters.memory import MemoryApprovals
from backend.kernel.logger import Logger
from backend.practice.adapters.memory import MemoryAuth, MemoryPractice


@dataclass(frozen=True)
class Loop:
    approvals: MemoryApprovals
    practice: MemoryPractice
    auth: MemoryAuth
    logger: Logger


def compose() -> Loop:
    return Loop(
        approvals=MemoryApprovals(),
        practice=MemoryPractice(),
        auth=MemoryAuth(),
        logger=StdoutLogger(),
    )
