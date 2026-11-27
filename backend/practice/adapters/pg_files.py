"""File metadata in PostgreSQL. Bytes stay in K12_FILE_DIR. SQL stays here."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from backend.kernel.result import StoreFault

T = TypeVar("T")
_FILE_ID = re.compile(r"file-[0-9a-f]{16}\Z")
_PURPOSE = "page"


class PgFiles:
    def __init__(self, pool: object, directory: Path) -> None:
        self._pool = pool
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def add(self, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        file_id = "file-" + digest[:16]
        self._write_bytes(file_id, data)
        _run(
            self._pool,
            lambda conn: conn.execute(
                """
                INSERT INTO files (file_id, purpose, checksum) VALUES (%s, %s, %s)
                ON CONFLICT (file_id) DO UPDATE SET purpose = EXCLUDED.purpose, checksum = EXCLUDED.checksum
                """,
                (file_id, _PURPOSE, digest),
            ),
        )
        return file_id, digest

    def store_bytes(self, file_id: str, data: bytes) -> str:
        """Write the bytes only. The intake row inserts purpose=intake and does not rewrite a page row."""
        digest = hashlib.sha256(data).hexdigest()
        self._write_bytes(file_id, data)
        return digest

    def purpose(self, file_id: str) -> str | None:
        row = _run(
            self._pool,
            lambda conn: conn.execute(
                "SELECT purpose FROM files WHERE file_id = %s",
                (file_id,),
            ).fetchone(),
        )
        if row is None:
            return None
        return str(row[0])

    def delete_online_bytes(self, file_id: str) -> bool:
        """Unlink one intake file. The files row stays. A missing file is not an error."""
        if self.purpose(file_id) != "intake":
            return False
        path = self._path(file_id)
        if path is not None and path.is_file():
            path.unlink()
        return True

    def read(self, file_id: str) -> bytes | None:
        if _meta(self._pool, file_id) is None:
            return None
        path = self._path(file_id)
        if path is None or not path.is_file():
            return None
        return path.read_bytes()

    def require(self, file_id: str) -> bytes:
        found = self.read(file_id)
        if found is None:
            raise StoreFault("file_missing")
        return found

    def _write_bytes(self, file_id: str, data: bytes) -> None:
        path = self._dir / file_id
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    def _path(self, file_id: str) -> Path | None:
        if _FILE_ID.fullmatch(file_id) is None:
            return None
        return self._dir / file_id


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _meta(pool: object, file_id: str) -> str | None:
    row = _run(
        pool,
        lambda conn: conn.execute(
            "SELECT checksum FROM files WHERE file_id = %s",
            (file_id,),
        ).fetchone(),
    )
    if row is None:
        return None
    return str(row[0])
