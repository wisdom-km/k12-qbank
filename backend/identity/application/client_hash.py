"""Hashes for login limits. Callers do not log the raw values."""

from __future__ import annotations

from backend.identity.domain.digest import digest


def client_hashes(username: str, host: str, agent: str) -> tuple[str, str, str]:
    return digest(username), digest(host), digest(agent)
