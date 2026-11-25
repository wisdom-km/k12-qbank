"""Wire adapters. This file does not decide whether a paper may be issued."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path

from backend.bootstrap.audit_memory import MemoryAudit
from backend.bootstrap.error_ring import ErrorRing
from backend.bootstrap.file_log import FileLog
from backend.bootstrap.health import HealthReport, health_report
from backend.bootstrap.stdout_log import StdoutLogger
from backend.catalog.adapters.answer_memory import MemoryAnswers
from backend.catalog.adapters.draft_memory import MemoryDrafts
from backend.catalog.adapters.memory import MemoryApprovals
from backend.catalog.adapters.memory_books import MemoryBooks
from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.identity.adapters.argon2_hasher import Argon2Hasher
from backend.identity.adapters.authorizer import GrantAuthorizer
from backend.identity.adapters.log_audit import LogAudit
from backend.identity.adapters.memory import MemoryDb
from backend.identity.adapters.memory_rate_limiter import WindowLimiter
from backend.identity.adapters.stdlib_clock import SystemClock
from backend.identity.application.deps import Deps
from backend.identity.application.run import memory_scope
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import CompositeLogger, Logger
from backend.practice.adapters.files import MemoryFiles
from backend.ai.adapters.memory_runs import MemoryRuns
from backend.practice.adapters.memory_decision import MemoryDecisions
from backend.ai.adapters.mock_model import MockModel
from backend.practice.adapters.memory import MemoryPractice
from backend.practice.adapters.memory_intake import MemoryIntake
from backend.practice.adapters.memory_items import MemoryComposedWriter, MemoryPracticeItems
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.application.ports import PageRenderer

_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Loop:
    approvals: object
    practice: object
    auth: object
    logger: Logger
    files: object
    renderer: PageRenderer
    health: HealthReport
    identity: object | None = None
    deps: Deps | None = None
    errors: ErrorRing | None = None
    opener: object | None = None
    questions: object | None = None
    answers: object | None = None
    publications: object = field(default_factory=MemoryPublications)
    items: object = field(default_factory=MemoryPracticeItems)
    composed: object | None = None
    intake: object = field(default_factory=MemoryIntake)
    ai_runs: object = field(default_factory=MemoryRuns)
    model: object = field(default_factory=MockModel)
    decisions: object = field(default_factory=MemoryDecisions)
    books: object = field(default_factory=MemoryBooks)


def compose() -> Loop:
    """Memory adapters. PostgreSQL stays closed until K12_PG_DSN is set on the server path."""
    db = MemoryDb()
    errors = ErrorRing()
    runtime = _runtime_sinks()
    logger = CompositeLogger(runtime, db.audits, errors)
    deps = make_deps(db.attempts, logger)
    return _loop(
        auth=GrantAuthorizer(db.grants),
        logger=logger,
        errors=errors,
        identity=db,
        deps=deps,
        opener=lambda: memory_scope(db),
    )


def attach_identity(loop: Loop) -> Loop:
    """Give a caller-built loop a memory identity without dropping its practice doubles."""
    if loop.identity is not None and loop.deps is not None and loop.opener is not None:
        return loop
    db = MemoryDb()
    errors = loop.errors or getattr(loop.logger, "errors", None) or ErrorRing()
    deps = make_deps(db.attempts, loop.logger)
    return replace(
        loop,
        auth=GrantAuthorizer(db.grants),
        identity=db,
        deps=deps,
        errors=errors if isinstance(errors, ErrorRing) else ErrorRing(),
        opener=lambda: memory_scope(db),
    )


def make_deps(attempts: object, logger: Logger) -> Deps:
    enabled = os.environ.get("K12_RATE_LIMIT_LOGIN", "1") != "0"
    return Deps(
        clock=SystemClock(),
        hasher=Argon2Hasher(),
        limiter=WindowLimiter(attempts, enabled=enabled),  # type: ignore[arg-type]
        audit=LogAudit(logger),
        logger=logger,
        idle=timedelta(minutes=_env_int("K12_SESSION_IDLE_MINUTES", 60)),
        absolute=timedelta(hours=_env_int("K12_SESSION_ABSOLUTE_HOURS", 12)),
    )


def repo_root() -> Path:
    return _ROOT


def _loop(**kwargs: object) -> Loop:
    values: dict[str, object] = {
        "approvals": MemoryApprovals(),
        "practice": MemoryPractice(),
        "files": MemoryFiles(),
        "renderer": StdPdf(),
        "health": health_report(),
        "questions": MemoryDrafts(),
        "answers": MemoryAnswers(),
    }
    values.update(kwargs)
    if "ai_runs" not in values:
        values["ai_runs"] = MemoryRuns()
    if "decisions" not in values:
        values["decisions"] = MemoryDecisions()
    if "model" not in values:
        from backend.bootstrap.ai_wire import build_model

        values["model"] = build_model()
    loop = Loop(**values)  # type: ignore[arg-type]
    if loop.composed is None:
        loop = replace(loop, composed=MemoryComposedWriter(loop.practice, loop.items))  # type: ignore[arg-type]
    attach = getattr(loop.publications, "attach_approvals", None)
    if attach is not None:
        attach(loop.approvals)
    return loop


def _runtime_sinks() -> list[Logger]:
    runtime: list[Logger] = [StdoutLogger()]
    if os.environ.get("K12_LOG_FILE", "1") != "0":
        directory = Path(os.environ.get("K12_LOG_DIR", "./var/log/k12"))
        runtime.append(FileLog(directory, retain_days=_env_int("K12_LOG_RETAIN_DAYS", 14)))
    return runtime


def build_logger(audit: object | None = None) -> Logger:
    """Stdout, optional file, and an in-memory audit sink. Used by the retention script."""
    runtime = _runtime_sinks()
    sink = audit if audit is not None else MemoryAudit()
    return CompositeLogger(runtime, sink, ErrorRing())  # type: ignore[arg-type]


class FanLog:
    """One runtime logger for the audit fallback report."""

    def __init__(self, sinks: list[Logger]) -> None:
        self._sinks = list(sinks)

    def log(self, event: LogEvent) -> None:
        for sink in self._sinks:
            sink.log(event)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 1:
        return default
    return value
