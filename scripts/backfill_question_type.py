"""Copy approvals.type onto unresolved question rows.

Usage: python scripts/backfill_question_type.py --dry-run
       python scripts/backfill_question_type.py --apply

check.ps1 and CI do not pass --apply.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.catalog.adapters.pg_question_type import (  # noqa: E402
    apply_question_types,
    question_type_counts,
)


def main(argv: list[str]) -> int:
    flag = argv[1] if len(argv) == 2 else ""
    if flag not in {"--dry-run", "--apply"}:
        print("usage: python scripts/backfill_question_type.py --dry-run|--apply")
        return 2
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        print("K12_PG_DSN is empty")
        return 2
    import psycopg

    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                counts = question_type_counts(conn)
                updated = apply_question_types(conn) if flag == "--apply" else 0
    except Exception as exc:
        print(_safe(exc))
        return 1
    print(f"scanned {counts['scanned']}")
    print(f"eligible {counts['eligible']}")
    print(f"skipped_missing {counts['skipped_missing']}")
    print(f"skipped_shape {counts['skipped_shape']}")
    print(f"would_update {counts['eligible'] if flag == '--dry-run' else updated}")
    print(f"updated {updated}")
    return 0


def _safe(exc: BaseException) -> str:
    text = str(exc).splitlines()[0] if str(exc) else ""
    if "postgresql://" in text or "password" in text.lower():
        return type(exc).__name__
    return type(exc).__name__ if not text else f"{type(exc).__name__}: {text}"


if __name__ == "__main__":
    sys.exit(main(sys.argv))
