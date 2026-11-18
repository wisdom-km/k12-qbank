"""One-way digests for rate limits. Callers do not log the input."""

from __future__ import annotations

import hashlib


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
