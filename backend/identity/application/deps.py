"""Injected clocks, hashers, and writers. One bundle per process."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from backend.identity.application.ports import AuditWriter, Clock, PasswordHasher, RateLimiter
from backend.kernel.logger import Logger


@dataclass(frozen=True)
class Deps:
    clock: Clock
    hasher: PasswordHasher
    limiter: RateLimiter
    audit: AuditWriter
    logger: Logger
    idle: timedelta
    absolute: timedelta
