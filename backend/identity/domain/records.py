"""Plain records. No hashing and no database types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    role: str
    status: str
    password_hash: str
    password_algo: str
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None = None


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str
    grade: str
    subject_id: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Session:
    session_id: str
    user_id: str
    csrf_token: str
    issued_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    user_agent_hash: str = ""
    ip_hash: str = ""


@dataclass(frozen=True)
class Grant:
    grant_id: str
    teacher_id: str
    student_id: str
    subject_id: str
    granted_by: str
    granted_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class AuditRecord:
    occurred_at: datetime
    request_id: str
    actor_user_id: str
    actor_role: str
    action: str
    target_kind: str
    target_id: str
    reason_code: str
    outcome: str
