"""Delete expired runtime files, audit rows, and login attempts."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.bootstrap.file_log import FileLog
from backend.kernel.logger import Logger
from backend.kernel.use_log import emit


def sweep(directory: Path, log_days: int, audit_days: int, dsn: str, logger: Logger) -> int:
    started = time.perf_counter()
    try:
        removed = FileLog(directory, retain_days=log_days).purge()
        if dsn.strip():
            _purge_rows(dsn.strip(), log_days, audit_days)
    except Exception:
        emit(
            logger,
            level="ERROR",
            event="log_retention_swept",
            request_id="retention",
            module="retention",
            outcome="err",
            started=started,
        )
        raise
    emit(
        logger,
        level="INFO",
        event="log_retention_swept",
        request_id="retention",
        module="retention",
        outcome="ok",
        started=started,
    )
    return removed


def days_of(raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 1:
        return default
    return value


def _purge_rows(dsn: str, log_days: int, audit_days: int) -> None:
    from backend.identity.adapters.pg_store import purge_expired

    now = datetime.now(timezone.utc)
    purge_expired(dsn, now - timedelta(days=audit_days), now - timedelta(days=log_days))
