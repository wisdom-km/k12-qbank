"""One identity world for memory, and another for PostgreSQL."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from backend.identity.adapters.log_audit import LogAudit
from backend.identity.adapters.memory import MemoryDb
from backend.identity.adapters.memory_rate_limiter import WindowLimiter
from backend.identity.application.deps import Deps
from backend.identity.application.run import execute, memory_scope
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import CompositeLogger
from backend.kernel.result import Err, Ok

ROOT = Path(__file__).resolve().parents[2]
Work = Callable[[object], Ok[object] | Err]


class FixedClock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment

    def advance(self, delta: timedelta) -> None:
        self.moment = self.moment + delta


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class FakeHasher:
    def hash(self, secret: str) -> str:
        return "v1:" + secret

    def verify(self, secret: str, stored: str) -> bool:
        return stored in {"v1:" + secret, "old:" + secret}

    def needs_rehash(self, stored: str) -> bool:
        return stored.startswith("old:")


@dataclass
class World:
    clock: FixedClock
    deps: Deps
    runtime: ListLog
    run: Callable[..., Ok[object] | Err]
    audit_count: Callable[[], int]
    audit_text: Callable[[], str]
    rolls_back: bool


def memory_world(idle: timedelta | None = None, absolute: timedelta | None = None) -> World:
    db = MemoryDb()
    runtime = ListLog()
    logger = CompositeLogger([runtime], db.audits)
    clock = FixedClock(datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc))
    deps = _deps(clock, db.attempts, logger, idle, absolute)

    def run(work: Work, request_id: str = "req") -> Ok[object] | Err:
        return execute(lambda: memory_scope(db), work, logger, request_id)

    def audit_count() -> int:
        return len(db.audits.rows)

    def audit_text() -> str:
        names = " ".join(event.event for event in db.audits.events)
        body = " ".join(
            " ".join((row.action, row.outcome, row.reason_code, row.target_kind, row.target_id))
            for row in db.audits.rows
        )
        return names + " " + body

    return World(clock, deps, runtime, run, audit_count, audit_text, False)


def pg_world(idle: timedelta | None = None, absolute: timedelta | None = None) -> World:
    pool = _pool()
    _truncate(pool)
    runtime = ListLog()
    from backend.bootstrap.audit_pg import AuditPg
    from backend.identity.adapters.pg_store import PgAttempts

    fallback = ROOT / "var" / "log" / "k12" / "audit-fallback.jsonl"
    sink = AuditPg(pool, runtime, fallback)
    logger = CompositeLogger([runtime], sink)
    clock = FixedClock(datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc))
    deps = _deps(clock, PgAttempts(pool), logger, idle, absolute)

    def run(work: Work, request_id: str = "req") -> Ok[object] | Err:
        return execute(lambda: _scope(pool), work, logger, request_id)

    return World(clock, deps, runtime, run, lambda: _scalar(pool, "SELECT count(*) FROM audit_events"), lambda: _audit_text(pool), True)


def _deps(clock: FixedClock, attempts: object, logger: CompositeLogger, idle: timedelta | None, absolute: timedelta | None) -> Deps:
    return Deps(
        clock=clock,
        hasher=FakeHasher(),
        limiter=WindowLimiter(attempts),  # type: ignore[arg-type]
        audit=LogAudit(logger),
        logger=logger,
        idle=idle or timedelta(minutes=60),
        absolute=absolute or timedelta(hours=12),
    )


@contextmanager
def _scope(pool: object) -> Iterator[object]:
    from backend.identity.adapters.pg_store import PgDb

    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            yield PgDb(conn, pool)


def _pool() -> object:
    global _POOL
    if _POOL is not None:
        return _POOL
    from psycopg_pool import ConnectionPool

    from backend.bootstrap.migrate import migrate

    dsn = os.environ["K12_PG_DSN"]
    migrate(dsn, ROOT, "up")
    _POOL = ConnectionPool(dsn, min_size=1, max_size=4, open=True)
    return _POOL


def _truncate(pool: object) -> None:
    statement = """
        TRUNCATE TABLE teacher_grants, sessions, login_attempts, audit_events, students, users
        RESTART IDENTITY CASCADE
    """
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement)


def _scalar(pool: object, statement: str) -> int:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            row = conn.execute(statement).fetchone()
    return int(row[0])


def _audit_text(pool: object) -> str:
    statement = """
        SELECT action, outcome, COALESCE(reason_code, ''), COALESCE(target_kind, ''),
               COALESCE(target_id, ''), COALESCE(detail_json::text, '')
        FROM audit_events
        ORDER BY event_id
    """
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            rows = conn.execute(statement).fetchall()
    return " ".join(" ".join(str(part) for part in row) for row in rows)


_POOL: object | None = None
