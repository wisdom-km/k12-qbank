"""Current entry command. Does not start the teaching service."""

from __future__ import annotations


def main() -> int:
    print(
        "k12-qbank local synthetic HTTP. tier=long. real student data=yes. "
        "reachable by teachers=yes. PostgreSQL connects only when K12_PG_DSN is set. "
        "This command does not start the site."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
