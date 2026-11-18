"""Delete expired log files and audit rows. Reads K12_* from the environment."""

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
    dsn = os.environ.get("K12_PG_DSN", "")
    sweep(directory, log_days, audit_days, dsn, build_logger())
    return 0


if __name__ == "__main__":
    sys.exit(main())
