"""Choose memory or PostgreSQL from K12_ENV. The log line never carries the DSN."""

from __future__ import annotations

import time

from backend.kernel.logger import Logger
from backend.kernel.use_log import emit


def choose_persist(env_raw: str, dsn: str, logger: Logger) -> bool:
    """Return True when this process must connect. A refused mode exits."""
    mode = _mode(env_raw, logger)
    if mode == "production" and not dsn.strip():
        _refuse(logger, "dsn_required")
    if mode == "development" and not dsn.strip():
        _warn_memory(logger)
        return False
    return True


def require_file_dir(env_raw: str, directory: str, logger: Logger) -> None:
    """production with no page-byte directory exits before a connection."""
    if _mode(env_raw, logger) == "production" and not directory.strip():
        _refuse(logger, "file_dir_required")


def _mode(env_raw: str, logger: Logger) -> str:
    mode = env_raw.strip() or "development"
    if mode not in {"development", "production"}:
        _refuse(logger, "bad_env")
    return mode


def _refuse(logger: Logger, outcome: str) -> None:
    emit(
        logger,
        level="ERROR",
        event="startup_refused",
        request_id="boot",
        module="bootstrap",
        outcome=outcome,
        started=time.perf_counter(),
    )
    raise SystemExit(1)


def _warn_memory(logger: Logger) -> None:
    emit(
        logger,
        level="WARN",
        event="startup_degraded",
        request_id="boot",
        module="bootstrap",
        outcome="memory",
        started=time.perf_counter(),
    )
