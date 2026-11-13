"""Dependency direction and file-size cap. See ARCHITECTURE.md 依赖允许表."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SLICES = ("catalog", "knowledge", "identity", "practice", "analysis", "delivery")
HARD_LINE_CAP = 800
FORBIDDEN_MODULES = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "httpx",
    "requests",
    "openai",
    "anthropic",
}


def fail(message: str) -> None:
    print(f"LINT FAIL: {message}")
    print(
        "Fix: domain and application may import kernel and their own slice only. "
        "Other slices are reached through that slice's api.py. "
        "See ARCHITECTURE.md dependency table. Do not add utils or helpers."
    )
    raise SystemExit(1)


def slice_of(path: Path) -> str | None:
    parts = path.relative_to(BACKEND).parts
    return parts[0] if parts and parts[0] in SLICES else None


def layer_of(path: Path) -> str | None:
    parts = set(path.relative_to(BACKEND).parts)
    for name in ("domain", "application", "adapters"):
        if name in parts:
            return name
    return None


def imported_modules(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def check_file(path: Path) -> None:
    rel = path.relative_to(ROOT).as_posix()
    source = path.read_text(encoding="utf-8")
    if len(source.splitlines()) > HARD_LINE_CAP:
        fail(f"{rel} has more than {HARD_LINE_CAP} lines. Split by what it hides, or record an ADR.")
    here = slice_of(path)
    layer = layer_of(path)
    in_kernel = rel.startswith("backend/kernel/")
    if here is None and layer is None and not in_kernel:
        return
    tree = ast.parse(source, filename=rel)
    for module in imported_modules(tree):
        root_name = module.split(".", 1)[0]
        protected = layer in {"domain", "application"} or in_kernel
        if protected and root_name in FORBIDDEN_MODULES:
            fail(f"{rel} imports {module}. Keep frameworks in adapters or the composition root.")
        if not module.startswith("backend."):
            continue
        parts = module.split(".")
        other = parts[1] if len(parts) > 1 else ""
        if in_kernel and other in SLICES:
            fail(f"{rel} imports {module}. Kernel must not depend on a business slice.")
        if layer == "domain" and here is not None:
            allowed = module.startswith("backend.kernel") or module.startswith(f"backend.{here}.domain")
            if not allowed:
                fail(f"{rel} imports {module}. Domain may import only kernel and its own domain package.")
        if layer == "application" and here is not None:
            if other == "adapters" or ".adapters" in module:
                fail(f"{rel} imports {module}. Application depends on ports, not adapters.")
            if other in SLICES and other != here and not (
                module == f"backend.{other}.api" or module.startswith(f"backend.{other}.api.")
            ):
                fail(f"{rel} imports {module}. Import backend.{other}.api only.")
        if layer == "adapters" and here is not None and other in SLICES and other != here:
            if not (module == f"backend.{other}.api" or module.startswith(f"backend.{other}.api.")):
                fail(f"{rel} imports {module}. Adapters do not reach into another slice.")


def main() -> int:
    if BACKEND.is_dir():
        for banned in ("utils", "helpers", "common"):
            for folder in BACKEND.rglob(banned):
                if folder.is_dir():
                    fail(f"remove {folder.relative_to(ROOT).as_posix()}. Do not create a junk drawer.")
        for path in BACKEND.rglob("*.py"):
            check_file(path)
    print("LINT PASS: dependency direction and file-size cap hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
