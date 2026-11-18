"""Public identity types. Other slices import this module and nothing under it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.kernel.result import Err

INVALID_CREDENTIALS = "invalid_credentials"
ACCOUNT_LOCKED = "account_locked"
IP_THROTTLED = "ip_throttled"
USERNAME_TAKEN = "username_taken"
WEAK_PASSWORD = (
    "weak_password"
)
NOT_FOUND = "not_found"
PERMISSION_DENIED = "permission_denied"
VALIDATION_FAILED = "validation_failed"
ALREADY_GRANTED = "already_granted"
NOT_GRANTED = "not_granted"
STORE_FAILED = "store_failed"
UNAUTHENTICATED = "unauthenticated"


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: str
    username: str


class RequireActor(Protocol):
    def __call__(self, actor: Actor | None) -> Actor | Err:
        """Return the actor, or Err when the request has no session."""


def require_actor(actor: Actor | None) -> Actor | Err:
    if actor is None:
        return Err(UNAUTHENTICATED, "sign in")
    return actor


@dataclass(frozen=True)
class LoginCommand:
    username: str
    secret: str
    username_hash: str
    ip_hash: str
    user_agent_hash: str = ""


@dataclass(frozen=True)
class AuditQuery:
    limit: int = 50
    offset: int = 0
    action: str = ""
    actor_user_id: str = ""
    since: datetime | None = None
    until: datetime | None = None


__all__ = [
    "ACCOUNT_LOCKED",
    "ALREADY_GRANTED",
    "Actor",
    "AuditQuery",
    "INVALID_CREDENTIALS",
    "IP_THROTTLED",
    "LoginCommand",
    "NOT_FOUND",
    "NOT_GRANTED",
    "PERMISSION_DENIED",
    "RequireActor",
    "STORE_FAILED",
    "UNAUTHENTICATED",
    "USERNAME_TAKEN",
    "VALIDATION_FAILED",
    "WEAK_PASSWORD",
    "require_actor",
]
