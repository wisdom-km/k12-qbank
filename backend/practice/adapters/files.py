"""In-memory file bytes for the synthetic PDF. The id is the content hash prefix."""

from __future__ import annotations

import hashlib
import threading

from backend.kernel.result import StoreFault


class MemoryFiles:
    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}
        self._sums: dict[str, str] = {}
        self._purpose: dict[str, str] = {}
        self._lock = threading.Lock()

    def add(self, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        file_id = "file-" + digest[:16]
        self.store_bytes(file_id, data)
        with self._lock:
            self._purpose[file_id] = "page"
        return file_id, digest

    def store_bytes(self, file_id: str, data: bytes) -> str:
        """Keep bytes for an id the caller already chose. Does not rewrite a page purpose."""
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            self._items[file_id] = data
            self._sums[file_id] = digest
            self._purpose.setdefault(file_id, "intake")
        return digest

    def purpose(self, file_id: str) -> str | None:
        with self._lock:
            return self._purpose.get(file_id)

    def delete_online_bytes(self, file_id: str) -> bool:
        """Drop intake bytes only. The checksum and purpose stay. A missing file is fine."""
        with self._lock:
            if self._purpose.get(file_id) != "intake":
                return False
            self._items.pop(file_id, None)
        return True

    def read(self, file_id: str) -> bytes | None:
        with self._lock:
            return self._items.get(file_id)

    def checksum(self, file_id: str) -> str | None:
        with self._lock:
            return self._sums.get(file_id)

    def require(self, file_id: str) -> bytes:
        found = self.read(file_id)
        if found is None:
            raise StoreFault("file_missing")
        return found
