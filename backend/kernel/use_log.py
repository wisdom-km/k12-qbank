"""One helper for use-case logs. No business rules and no I/O of its own."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok

T = TypeVar("T")


def emit(
    logger: Logger,
    *,
    level: str,
    event: str,
    request_id: str,
    module: str,
    outcome: str,
    started: float,
) -> None:
    elapsed = int((time.perf_counter() - started) * 1000)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    logger.log(
        LogEvent(
            time=now,
            level=level,
            event=event,
            request_id=request_id,
            module=module,
            outcome=outcome,
            duration_ms=elapsed,
        )
    )


def read_store(
    action: Callable[[], T],
    logger: Logger,
    request_id: str,
    module: str,
    started: float,
) -> Ok[T] | Err:
    try:
        return Ok(action())
    except Exception:
        emit(
            logger,
            level="ERROR",
            event="use_case_failed",
            request_id=request_id,
            module=module,
            outcome="store_failed",
            started=started,
        )
        return Err("store_failed", "the store failed")
