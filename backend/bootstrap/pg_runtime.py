"""Open PostgreSQL when K12_PG_DSN is set. A failure exits without printing the DSN."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.bootstrap.compose import FanLog, Loop, _loop, _runtime_sinks, make_deps
from backend.bootstrap.error_ring import ErrorRing
from backend.bootstrap.run_mode import require_file_dir
from backend.bootstrap.stdout_log import StdoutLogger
from backend.identity.adapters.authorizer import GrantAuthorizer, PoolGrantReader
from backend.kernel.logger import CompositeLogger
from backend.kernel.use_log import emit


def open_postgres() -> Loop:
    require_file_dir(
        os.environ.get("K12_ENV", ""),
        os.environ.get("K12_FILE_DIR", ""),
        StdoutLogger(),
    )
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    pool = _pool_or_exit(dsn)
    runtime = _runtime_sinks()
    errors = ErrorRing()
    directory = Path(os.environ.get("K12_LOG_DIR", "./var/log/k12"))
    from backend.bootstrap.audit_pg import AuditPg

    audit = AuditPg(pool, FanLog(runtime), directory / "audit-fallback.jsonl")
    logger = CompositeLogger(runtime, audit, errors)
    from backend.identity.adapters.pg_store import PgAttempts

    attempts = PgAttempts(pool)
    deps = make_deps(attempts, logger)
    approvals, practice, files, items, intake = _catalog_stores(pool)
    from backend.ai.adapters.pg_runs import PgRuns
    from backend.practice.adapters.pg_decision import PgDecisions
    from backend.catalog.adapters.pg_answers import PgAnswers
    from backend.catalog.adapters.pg_books import PgBooks
    from backend.catalog.adapters.pg_publications import PgPublications
    from backend.catalog.adapters.pg_questions import PgQuestions

    return _loop(
        auth=GrantAuthorizer(PoolGrantReader(pool)),  # type: ignore[arg-type]
        logger=logger,
        errors=errors,
        identity=pool,
        deps=deps,
        opener=lambda: _scope(pool),
        approvals=approvals,
        practice=practice,
        files=files,
        questions=PgQuestions(pool),
        answers=PgAnswers(pool),
        publications=PgPublications(pool),
        items=items,
        composed=items,
        intake=intake,
        ai_runs=PgRuns(pool),
        decisions=PgDecisions(pool),
        books=PgBooks(pool),
    )


def _catalog_stores(pool: object) -> tuple[object, object, object, object, object]:
    """DSN path stores approvals and papers in PostgreSQL. Empty K12_FILE_DIR keeps bytes in memory."""
    from backend.catalog.adapters.pg_approvals import PgApprovals
    from backend.practice.adapters.files import MemoryFiles
    from backend.practice.adapters.pg_files import PgFiles
    from backend.practice.adapters.pg_intake import PgIntake
    from backend.practice.adapters.pg_items import PgPracticeItems
    from backend.practice.adapters.pg_practice import PgPractice

    directory = os.environ.get("K12_FILE_DIR", "").strip()
    if directory:
        files: object = PgFiles(pool, Path(directory))
    else:
        emit(
            StdoutLogger(),
            level="WARN",
            event="startup_degraded",
            request_id="boot",
            module="bootstrap",
            outcome="memory_files",
            started=time.perf_counter(),
        )
        files = MemoryFiles()
    return PgApprovals(pool), PgPractice(pool), files, PgPracticeItems(pool), PgIntake(pool)


@contextmanager
def _scope(pool: object) -> Iterator[object]:
    from backend.identity.adapters.pg_store import PgDb

    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            yield PgDb(conn, pool)


def _pool_or_exit(dsn: str) -> object:
    started = time.perf_counter()
    try:
        return _open_pool(dsn)
    except Exception:
        emit(
            StdoutLogger(),
            level="ERROR",
            event="use_case_failed",
            request_id="boot",
            module="bootstrap",
            outcome="store_failed",
            started=started,
        )
        raise SystemExit(1) from None


def _open_pool(dsn: str) -> object:
    import psycopg
    from psycopg_pool import ConnectionPool

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import migrate

    with psycopg.connect(dsn, connect_timeout=3, autocommit=True):
        pass
    migrate(dsn, repo_root(), "up")
    return ConnectionPool(
        dsn,
        min_size=_size("K12_PG_POOL_MIN", 1),
        max_size=_size("K12_PG_POOL_MAX", 5),
        timeout=5,
        open=True,
        kwargs={"connect_timeout": 3},
    )


def _size(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 1:
        return default
    return value
