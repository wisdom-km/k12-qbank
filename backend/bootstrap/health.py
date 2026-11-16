"""Fixed health body for GET /health.

The composition root serves this value. status=ok means the process answered.
It does not mean a database or a model is ready. There is no database in this
slice. The body is status only: no secrets, no connection strings, no student data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthReport:
    status: str


def health_report() -> HealthReport:
    """The process can answer. Dependency checks wait until a database exists."""
    return HealthReport(status="ok")
