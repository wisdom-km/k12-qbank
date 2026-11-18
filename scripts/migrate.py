"""Apply shipped SQL migrations. Usage: python scripts/migrate.py up|down"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.bootstrap.migrate import migrate  # noqa: E402


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "up"
    if command not in {"up", "down"}:
        print("usage: python scripts/migrate.py up|down")
        return 2
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        print("K12_PG_DSN is empty")
        return 2
    applied = migrate(dsn, ROOT, command)
    print(command if not applied else command + " " + " ".join(applied))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
