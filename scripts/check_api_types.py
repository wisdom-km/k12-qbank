"""Regenerate apps/web/src/api.types.ts and compare it to the committed file.

The default HTTP app keeps OpenAPI closed. This script builds a schema in
memory and does not listen. Pass --write to refresh the committed file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_openapi import schema_text  # noqa: E402
COMMITTED = ROOT / "apps" / "web" / "src" / "api.types.ts"


def npm_command(args: list[str]) -> str | list[str]:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm not found")
    command = [npm, *args]
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return command


def generate(spec: Path, destination: Path) -> None:
    spec.write_text(schema_text(), encoding="utf-8", newline="\n")
    completed = subprocess.run(
        npm_command(
            [
                "exec",
                "--prefix",
                str(ROOT / "apps" / "web"),
                "--",
                "openapi-typescript",
                str(spec),
                "-o",
                str(destination),
            ]
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        shell=os.name == "nt",
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def main() -> int:
    write = "--write" in sys.argv[1:]
    with tempfile.TemporaryDirectory() as directory:
        spec = Path(directory) / "openapi.json"
        generated = Path(directory) / "api.types.ts"
        generate(spec, generated)
        fresh = normalize(generated.read_text(encoding="utf-8"))
    if write:
        COMMITTED.write_text(fresh, encoding="utf-8", newline="\n")
        print(f"wrote {COMMITTED.relative_to(ROOT).as_posix()}")
        return 0
    if not COMMITTED.is_file():
        print("missing apps/web/src/api.types.ts. Run: python scripts/check_api_types.py --write")
        return 1
    current = normalize(COMMITTED.read_text(encoding="utf-8"))
    if current != fresh:
        print("apps/web/src/api.types.ts does not match the OpenAPI export.")
        print("Run: python scripts/check_api_types.py --write")
        return 1
    print("api types match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
