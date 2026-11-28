"""Delete expired log files, sessions, and login attempts. Reads K12_* from the environment.

Intake photos are not deleted here. They need a passphrase and an archive
directory, so that job is scripts/archive_intake.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.bootstrap.compose import build_logger  # noqa: E402
from backend.bootstrap.retention import days_of, sweep  # noqa: E402


def main() -> int:
    directory = Path(os.environ.get("K12_LOG_DIR", "./var/log/k12"))
    log_days = days_of(os.environ.get("K12_LOG_RETAIN_DAYS"), 14)
    audit_days = days_of(os.environ.get("K12_AUDIT_RETAIN_DAYS"), 1825)
    session_days = days_of(os.environ.get("K12_SESSION_RETAIN_DAYS"), 30)
    attempt_days = days_of(os.environ.get("K12_LOGIN_ATTEMPT_RETAIN_DAYS"), 30)
    dsn = os.environ.get("K12_PG_DSN", "")
    sweep(
        directory,
        log_days,
        audit_days,
        dsn,
        build_logger(),
        session_days=session_days,
        attempt_days=attempt_days,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
