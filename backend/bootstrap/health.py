"""Fixed health body for GET /health and GET /health/live.

The composition root serves this value. status=ok means the process answered.
This body does not check the database. Readiness is GET /health/ready.
The body is status only: no secrets, no connection strings, no student data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthReport:
    status: str


def health_report() -> HealthReport:
    """The process can answer. This body does not check the database."""
    return HealthReport(status="ok")
