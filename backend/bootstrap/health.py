"""Fixed health body for the future GET /health route.

There is no HTTP server in this slice. The composition root holds this value
so the route can call health_report() later without inventing a second shape.
The body is status only: no secrets, no connection strings, no student data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthReport:
    status: str


def health_report() -> HealthReport:
    """The process can answer. Dependency checks wait until a database exists."""
    return HealthReport(status="ok")
