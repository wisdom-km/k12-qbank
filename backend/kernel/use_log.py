"""One helper for use-case logs. No business rules and no I/O of its own."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok, StoreFault

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
    actor_user_id: str = "",
    target_kind: str = "",
    target_id: str = "",
    audit: bool = False,
    detail: str = "",
    action: str = "",
    actor_role: str = "",
) -> None:
    elapsed = int((time.perf_counter() - started) * 1000)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    event_row = LogEvent(
        time=now,
        level=level,
        event=event,
        request_id=request_id,
        module=module,
        outcome=outcome,
        duration_ms=elapsed,
        actor_user_id=actor_user_id,
        target_kind=target_kind,
        target_id=target_id,
        audit=audit,
        actor_role=actor_role,
        action=action,
        detail=detail,
    )
    try:
        logger.log(event_row)
    except Exception:
        degraded = LogEvent(
            time=now,
            level="ERROR",
            event="log_failed",
            request_id=request_id,
            module=module,
            outcome="log_degraded",
            duration_ms=elapsed,
        )
        try:
            logger.log(degraded)
        except Exception:
            return


def read_store(
    action: Callable[[], T],
    logger: Logger,
    request_id: str,
    module: str,
    started: float,
) -> Ok[T] | Err:
    try:
        return Ok(action())
    except StoreFault as fault:
        return Err(fault.code, fault.code)
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
