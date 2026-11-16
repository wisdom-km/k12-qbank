"""In-memory file bytes for the synthetic PDF. The id is the content hash prefix."""

from __future__ import annotations

import hashlib
import threading


class MemoryFiles:
    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}
        self._sums: dict[str, str] = {}
        self._lock = threading.Lock()

    def add(self, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        file_id = "file-" + digest[:16]
        with self._lock:
            self._items[file_id] = data
            self._sums[file_id] = digest
        return file_id, digest

    def read(self, file_id: str) -> bytes | None:
        with self._lock:
            return self._items.get(file_id)

    def checksum(self, file_id: str) -> str | None:
        with self._lock:
            return self._sums.get(file_id)
