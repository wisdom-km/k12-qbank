"""Dependency direction, file-size cap, and first-slice scope.

See ARCHITECTURE.md 依赖允许表 and 禁止 F-02, F-03, F-04, F-10, F-11, F-13, F-14.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SLICES = ("catalog", "knowledge", "identity", "practice", "analysis", "delivery")
# First slice only. Widen this in the same change as the exec plan and ARCHITECTURE.
PHASE_TOP = {"kernel", "bootstrap", "catalog", "practice"}
KNOWN_TOP = PHASE_TOP | set(SLICES)
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
FORBIDDEN_TREES = (
    "apps/android",
    "apps/desktop",
    "apps/ios",
    "android",
    "ios",
    "src-tauri",
)
APP_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".dart", ".vue", ".kt", ".kts"}
BACKEND_IMPORT = (
    "backend.kernel",
    "backend.catalog",
    "backend.knowledge",
    "backend.identity",
    "backend.practice",
    "backend.analysis",
    "backend.delivery",
    "backend.bootstrap",
)


def fail(code: str, message: str, fix: str) -> None:
    print(f"{code} FAIL: {message}")
    print(f"Fix: {fix}")
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
        fail(
            "F-10",
            f"{rel} has more than {HARD_LINE_CAP} lines.",
            "Split the module by what it hides, or ask for a waiver in docs/WAIVERS.md plus an ADR. "
            "See ARCHITECTURE.md 文件大小.",
        )
    here = slice_of(path)
    layer = layer_of(path)
    in_kernel = rel.startswith("backend/kernel/")
    in_bootstrap = rel.startswith("backend/bootstrap/")
    if here is None and layer is None and not in_kernel and not in_bootstrap:
        return
    tree = ast.parse(source, filename=rel)
    for module in imported_modules(tree):
        root_name = module.split(".", 1)[0]
        protected = layer in {"domain", "application"} or in_kernel
        if protected and root_name in FORBIDDEN_MODULES:
            fail(
                "F-02",
                f"{rel} imports {module}.",
                "Keep frameworks, ORMs, and model SDKs in adapters or the composition root. "
                "See ARCHITECTURE.md 依赖允许表 and 禁止 F-02.",
            )
        if not module.startswith("backend."):
            continue
        parts = module.split(".")
        other = parts[1] if len(parts) > 1 else ""
        if in_kernel and other in SLICES:
            fail(
                "F-03",
                f"{rel} imports {module}.",
                "Kernel must not depend on a business slice. See ARCHITECTURE.md 依赖允许表.",
            )
        if in_bootstrap and other in SLICES and len(parts) >= 3 and parts[2] == "domain":
            fail(
                "F-11",
                f"{rel} imports {module}.",
                "The composition root wires application and adapters. It does not import domain. "
                "Business branches in the root are still review. See ARCHITECTURE.md 禁止 F-11.",
            )
        if layer == "domain" and here is not None:
            allowed = module.startswith("backend.kernel") or module.startswith(f"backend.{here}.domain")
            if not allowed:
                fail(
                    "F-03",
                    f"{rel} imports {module}.",
                    "Domain may import only kernel and its own domain package. "
                    "See ARCHITECTURE.md 依赖允许表.",
                )
        if layer == "application" and here is not None:
            if other == "adapters" or ".adapters" in module:
                fail(
                    "F-02",
                    f"{rel} imports {module}.",
                    "Application depends on ports, not adapters. See ARCHITECTURE.md 依赖允许表.",
                )
            if other in SLICES and other != here and not (
                module == f"backend.{other}.api" or module.startswith(f"backend.{other}.api.")
            ):
                fail(
                    "F-03",
                    f"{rel} imports {module}.",
                    f"Import backend.{other}.api only. See ARCHITECTURE.md 依赖允许表 and 禁止 F-03.",
                )
        if layer == "adapters" and here is not None and other in SLICES and other != here:
            if not (module == f"backend.{other}.api" or module.startswith(f"backend.{other}.api.")):
                fail(
                    "F-03",
                    f"{rel} imports {module}.",
                    "Adapters do not reach into another slice. Import that slice's api only. "
                    "See ARCHITECTURE.md 禁止 F-03.",
                )


def check_phase_scope() -> None:
    if BACKEND.is_dir():
        for child in BACKEND.iterdir():
            if not child.is_dir() or child.name == "__pycache__":
                continue
            rel = child.relative_to(ROOT).as_posix()
            if child.name not in KNOWN_TOP:
                fail(
                    "F-13",
                    f"{rel} is not a known backend package.",
                    "Use kernel, bootstrap, or one of: " + ", ".join(SLICES) + ". "
                    "See ARCHITECTURE.md 目录.",
                )
            if child.name not in PHASE_TOP:
                fail(
                    "F-13",
                    f"{rel} is outside the first slice.",
                    "The first slice may only add catalog and practice. "
                    "Change docs/exec-plans/active/rational-number-loop.md and ARCHITECTURE.md first, "
                    "then update PHASE_TOP in scripts/check_boundaries.py in that same change. "
                    "Do not widen the check just to make it pass.",
                )
    for rel in FORBIDDEN_TREES:
        if (ROOT / rel).exists():
            fail(
                "F-13",
                f"{rel} exists.",
                "The first slice is the browser only: no Android project and no desktop shell. "
                "See docs/exec-plans/active/rational-number-loop.md and ADR 0011.",
            )
    for path in ROOT.rglob("src-tauri"):
        if not path.is_dir() or ".git" in path.parts:
            continue
        fail(
            "F-13",
            f"{path.relative_to(ROOT).as_posix()} exists.",
            "Do not package a desktop shell in the first slice. See ADR 0011.",
        )
    for path in ROOT.rglob("package.json"):
        if ".git" in path.parts or "node_modules" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        deps: dict[str, object] = {}
        for key in ("dependencies", "devDependencies", "optionalDependencies"):
            value = data.get(key)
            if isinstance(value, dict):
                deps.update(value)
        if "electron" in deps:
            fail(
                "F-13",
                f"{path.relative_to(ROOT).as_posix()} depends on electron.",
                "Electron is not the fallback. Stay in the browser. See ADR 0011.",
            )


def check_apps_do_not_import_backend() -> None:
    apps = ROOT / "apps"
    if not apps.is_dir():
        return
    for path in apps.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in APP_EXTENSIONS:
            continue
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hit = "from backend" in text or "import backend" in text or "backend/" in text
        if not hit:
            hit = any(name in text for name in BACKEND_IMPORT)
        if hit:
            rel = path.relative_to(ROOT).as_posix()
            fail(
                "F-14",
                f"{rel} imports the backend tree.",
                "Web and apps call the service over HTTPS. They do not import kernel, domain, or adapters. "
                "See ARCHITECTURE.md 依赖允许表 and 禁止 F-14.",
            )


def main() -> int:
    if BACKEND.is_dir():
        for banned in ("utils", "helpers", "common"):
            for folder in BACKEND.rglob(banned):
                if folder.is_dir() and "__pycache__" not in folder.parts:
                    rel = folder.relative_to(ROOT).as_posix()
                    fail(
                        "F-04",
                        f"remove {rel}.",
                        "Do not create a junk drawer. See ARCHITECTURE.md 禁止 F-04.",
                    )
        for path in BACKEND.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            check_file(path)
    check_phase_scope()
    check_apps_do_not_import_backend()
    print("LINT PASS: dependency direction, file-size cap, and first-slice scope hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
