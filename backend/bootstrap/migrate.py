"""Apply forward-only SQL files. The runner owns schema_migrations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_VERSION = re.compile(r"(V\d+)__.+\.sql\Z")


@dataclass(frozen=True)
class Migration:
    version: str
    up: Path
    down: Path


def discover(root: Path) -> list[Migration]:
    found: dict[str, Migration] = {}
    base = root / "backend"
    for path in sorted(base.glob("*/migrations/V*.sql")):
        if path.name.endswith(".down.sql"):
            continue
        match = _VERSION.fullmatch(path.name)
        if match is None:
            continue
        version = match.group(1)
        if version in found:
            raise RuntimeError(f"duplicate migration version {version}")
        found[version] = Migration(version, path, path.with_name(path.stem + ".down.sql"))
    return sorted(found.values(), key=lambda item: int(item.version[1:]))


def sql_statements(script: str) -> list[str]:
    kept: list[str] = []
    for line in script.splitlines():
        if line.strip().startswith("--"):
            continue
        kept.append(line)
    return _split("\n".join(kept))


def migrate(dsn: str, root: Path, direction: str = "up") -> list[str]:
    if direction not in {"up", "down"}:
        raise ValueError(direction)
    import psycopg

    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        _ensure_book(conn)
        items = discover(root)
        have = _applied(conn)
        plan = _plan(items, have, direction)
        for item in plan:
            _apply(conn, item, direction)
            applied.append(item.version)
    return applied


def _plan(items: list[Migration], have: set[str], direction: str) -> list[Migration]:
    if direction == "up":
        return [item for item in items if item.version not in have]
    return [item for item in reversed(items) if item.version in have]


def _ensure_book(conn: object) -> None:
    with conn.transaction():  # type: ignore[attr-defined]
        conn.execute(  # type: ignore[attr-defined]
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL
            )
            """
        )


def _applied(conn: object) -> set[str]:
    with conn.transaction():  # type: ignore[attr-defined]
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()  # type: ignore[attr-defined]
    return {row[0] for row in rows}


def _apply(conn: object, item: Migration, direction: str) -> None:
    path = item.up if direction == "up" else item.down
    if not path.is_file():
        raise FileNotFoundError(path)
    with conn.transaction():  # type: ignore[attr-defined]
        for statement in sql_statements(path.read_text(encoding="utf-8")):
            conn.execute(statement)  # type: ignore[attr-defined]
        if direction == "up":
            conn.execute(  # type: ignore[attr-defined]
                "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, %s)",
                (item.version, datetime.now(timezone.utc)),
            )
            return
        conn.execute(  # type: ignore[attr-defined]
            "DELETE FROM schema_migrations WHERE version = %s",
            (item.version,),
        )


def _split(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    for char in body:
        if char == "'":
            quoted = not quoted
            current.append(char)
            continue
        if char == ";" and not quoted:
            text = "".join(current).strip()
            if text:
                parts.append(text)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts
