"""Current entry command. Does not start the teaching service."""

from __future__ import annotations


def main() -> int:
    print(
        "k12-qbank skeleton. tier=long. real student data=yes. "
        "reachable by teachers=yes. teaching service is not implemented. "
        "catalog and practice skeleton is in memory only."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
