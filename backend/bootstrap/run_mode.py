"""Choose memory or PostgreSQL from K12_ENV. The log line never carries the DSN."""

from __future__ import annotations

import time
from typing import NoReturn

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


_DEV_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def cors_origins(env_raw: str, raw: str | None, logger: Logger) -> tuple[str, ...]:
    """development defaults to the local page. production refuses an empty list.

    An empty or missing value is not ``*``. A list that contains ``*`` is refused
    in both modes, because credentials are on.
    """
    mode = _mode(env_raw, logger)
    text = "" if raw is None else raw.strip()
    if not text:
        if mode == "production":
            _refuse(logger, "cors_origins_required")
        return _DEV_ORIGINS
    items = tuple(part.strip() for part in text.split(",") if part.strip())
    if not items:
        if mode == "production":
            _refuse(logger, "cors_origins_required")
        return _DEV_ORIGINS
    if any(item == "*" for item in items):
        _refuse(logger, "cors_origin_wildcard")
    return items


def require_file_dir(env_raw: str, directory: str, logger: Logger) -> None:
    """production with no page-byte directory exits before a connection."""
    if _mode(env_raw, logger) == "production" and not directory.strip():
        _refuse(logger, "file_dir_required")


def _mode(env_raw: str, logger: Logger) -> str:
    mode = env_raw.strip() or "development"
    if mode not in {"development", "production"}:
        _refuse(logger, "bad_env")
    return mode


def _refuse(logger: Logger, outcome: str) -> NoReturn:
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
