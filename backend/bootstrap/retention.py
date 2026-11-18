"""Delete expired runtime files, sessions, audit rows, and login attempts."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.bootstrap.file_log import FileLog
from backend.kernel.logger import Logger
from backend.kernel.use_log import emit


def sweep(
    directory: Path,
    log_days: int,
    audit_days: int,
    dsn: str,
    logger: Logger,
    *,
    session_days: int = 30,
    attempt_days: int = 30,
) -> int:
    started = time.perf_counter()
    try:
        removed = FileLog(directory, retain_days=log_days).purge()
        counts = _purge_rows(dsn.strip(), audit_days, session_days, attempt_days) if dsn.strip() else ()
    except Exception:
        _swept(logger, started, "ERROR", "err")
        raise
    for count in counts:
        _swept(logger, started, "INFO", str(count))
    _swept(logger, started, "INFO", "ok")
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


def _swept(logger: Logger, started: float, level: str, outcome: str) -> None:
    emit(
        logger,
        level=level,
        event="log_retention_swept",
        request_id="retention",
        module="retention",
        outcome=outcome,
        started=started,
    )


def _purge_rows(dsn: str, audit_days: int, session_days: int, attempt_days: int) -> tuple[int, int, int]:
    from backend.identity.adapters.pg_retention import retain_rows

    now = datetime.now(timezone.utc)
    return retain_rows(
        dsn,
        now=now,
        audit_before=now - timedelta(days=audit_days),
        session_before=now - timedelta(days=session_days),
        attempt_before=now - timedelta(days=attempt_days),
    )
