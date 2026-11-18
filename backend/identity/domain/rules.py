"""Username, password, and status rules."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")
_SUBJECT = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def username_ok(value: str) -> bool:
    return bool(_USERNAME.fullmatch(value))


def password_ok(value: str) -> bool:
    if len(value) < 10 or len(value) > 128:
        return False
    has_letter = any(char.isalpha() for char in value)
    has_digit = any(char.isdigit() for char in value)
    return has_letter and has_digit


def subject_ok(value: str) -> bool:
    return bool(_SUBJECT.fullmatch(value))


def label_ok(value: str, limit: int) -> bool:
    text = value.strip()
    return bool(text) and len(text) <= limit


def can_disable(status: str) -> bool:
    return status == "active"


def can_enable(status: str) -> bool:
    return status == "disabled"


def can_archive(status: str) -> bool:
    return status == "active"


def session_usable(revoked_at: datetime | None, expires_at: datetime, last_seen_at: datetime, now: datetime, idle: timedelta) -> bool:
    if revoked_at is not None or now >= expires_at:
        return False
    return now - last_seen_at <= idle
