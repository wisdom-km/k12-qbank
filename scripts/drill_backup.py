"""File backup and restore drill. No database and no student data.

Writes a throwaway fixture, copies it with checksums, restores into a second
directory, and checks the checksums. Deletes the fixture when finished.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    started = time.perf_counter()
    root = Path(tempfile.mkdtemp(prefix="qbank-drill-"))
    try:
        source = root / "files"
        backup = root / "backup"
        restored = root / "restored"
        source.mkdir()
        (source / "page.txt").write_text("fixture-page", encoding="utf-8")
        (source / "note.txt").write_text("fixture-note", encoding="utf-8")
        expected = {path.name: sha256(path) for path in source.iterdir() if path.is_file()}

        backup.mkdir()
        for name in expected:
            shutil.copy2(source / name, backup / name)
        manifest = backup / "SHA256SUMS"
        lines = [f"{digest}  {name}" for name, digest in sorted(expected.items())]
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

        restored.mkdir()
        for name in expected:
            shutil.copy2(backup / name, restored / name)
        for name, digest in expected.items():
            got = sha256(restored / name)
            if got != digest:
                print(f"DRILL FAIL: {name} checksum {got} != {digest}")
                return 1
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        print(
            f"DRILL PASS: restored {len(expected)} fixture files. "
            f"elapsed_ms={elapsed_ms}. database=none. student_data=no."
        )
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
