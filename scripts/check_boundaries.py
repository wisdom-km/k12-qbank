"""Dependency direction, file-size cap, and phase scope.

Business slices allowed in this phase come from scripts/check.conf key
PHASE_SLICES. A non-empty PHASE_SLICES environment variable overrides that
line. A blank value uses catalog and practice. kernel and bootstrap are
always allowed and are not listed in PHASE_SLICES.

See ARCHITECTURE.md 依赖允许表 and 禁止 F-02, F-03, F-04, F-10, F-11, F-13, F-14.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SLICES = ("catalog", "knowledge", "identity", "practice", "analysis", "delivery")
ALWAYS_TOP = frozenset({"kernel", "bootstrap"})
DEFAULT_SLICES = frozenset({"catalog", "practice"})
KNOWN_TOP = ALWAYS_TOP | frozenset(SLICES)
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


class BoundaryError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


QUIET = False


def fail(code: str, message: str, fix: str) -> None:
    if not QUIET:
        print(f"{code} FAIL: {message}")
        print(f"Fix: {fix}")
    raise BoundaryError(code)


def slice_of(path: Path, backend: Path) -> str | None:
    parts = path.relative_to(backend).parts
    return parts[0] if parts and parts[0] in SLICES else None


def layer_of(path: Path, backend: Path) -> str | None:
    parts = set(path.relative_to(backend).parts)
    for name in ("domain", "application", "adapters"):
        if name in parts:
            return name
    return None


def package_parts(path: Path, backend: Path) -> list[str]:
    if path.parent == backend:
        return ["backend"]
    return ["backend", *path.parent.relative_to(backend).parts]


def resolve_from(path: Path, backend: Path, node: ast.ImportFrom) -> list[str]:
    if node.level == 0:
        return [node.module] if node.module else []
    parts = package_parts(path, backend)
    drop = node.level - 1
    if drop > len(parts):
        return ["<unresolved-relative>"]
    base = parts[: len(parts) - drop]
    if node.module:
        return [".".join([*base, *node.module.split(".")])]
    return [".".join([*base, alias.name]) for alias in node.names if alias.name != "*"]


def imported_modules(path: Path, tree: ast.AST, backend: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.extend(resolve_from(path, backend, node))
    return found


def check_file(path: Path, backend: Path = BACKEND) -> None:
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()
    source = path.read_text(encoding="utf-8")
    if len(source.splitlines()) > HARD_LINE_CAP:
        fail(
            "F-10",
            f"{rel} has more than {HARD_LINE_CAP} lines.",
            "Split the module by what it hides, or ask for a waiver in docs/WAIVERS.md plus an ADR. "
            "See ARCHITECTURE.md 文件大小.",
        )
    here = slice_of(path, backend)
    layer = layer_of(path, backend)
    inside = path.relative_to(backend).as_posix()
    in_kernel = inside.startswith("kernel/")
    in_bootstrap = inside.startswith("bootstrap/")
    if here is None and layer is None and not in_kernel and not in_bootstrap:
        return
    tree = ast.parse(source, filename=rel)
    for module in imported_modules(path, tree, backend):
        if module == "<unresolved-relative>":
            fail(
                "F-03",
                f"{rel} has a relative import that does not resolve inside backend.",
                "Write the import from the file's package with enough leading dots, "
                "or use an absolute backend import. See ARCHITECTURE.md 禁止 F-03.",
            )
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


def resolve_phase_slices(
    conf_value: str, env_value: str | None
) -> tuple[frozenset[str] | None, str, str]:
    """Return the allowed business slices, an error, and where the list came from.

    A non-empty env_value wins. A blank list uses catalog and practice.
    A name outside SLICES is an error so a typo does not silently widen the phase.
    """
    env = (env_value or "").strip()
    if env:
        raw, source = env, "env"
    else:
        raw, source = conf_value.strip(), "check.conf"
    tokens = raw.split()
    if not tokens:
        return frozenset(DEFAULT_SLICES), "", "default"
    unknown = [token for token in tokens if token not in SLICES]
    if unknown:
        return None, "unknown phase slice: " + " ".join(unknown), source
    return frozenset(tokens), "", source


def conf_value(key: str) -> str:
    """Last KEY=value in scripts/check.conf. The file is plain text, never executed."""
    path = ROOT / "scripts" / "check.conf"
    if not path.is_file():
        return ""
    found = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        found = value.strip()
        if len(found) >= 2 and found[0] == found[-1] and found[0] in {'"', "'"}:
            found = found[1:-1]
    return found


def current_phase() -> tuple[frozenset[str], str]:
    allowed, error, source = resolve_phase_slices(
        conf_value("PHASE_SLICES"),
        os.environ.get("PHASE_SLICES"),
    )
    if allowed is None:
        fail(
            "F-13",
            f"{error} (from {source}).",
            "PHASE_SLICES accepts only: " + ", ".join(SLICES) + ". "
            "Leave it blank to use catalog and practice. "
            "kernel and bootstrap are always allowed and are not written in the list. "
            "See scripts/check.conf.",
        )
    return allowed, source


def check_phase_scope() -> tuple[frozenset[str], str]:
    allowed, source = current_phase()
    phase_top = set(ALWAYS_TOP) | set(allowed)
    shown = " ".join(name for name in SLICES if name in allowed)
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
            if child.name not in phase_top:
                fail(
                    "F-13",
                    f"{rel} is outside the current phase ({shown}, from {source}).",
                    "The default phase allows catalog and practice. "
                    "kernel and bootstrap stay allowed. "
                    "Change docs/exec-plans/active/rational-number-loop.md and ARCHITECTURE.md first, "
                    "then set PHASE_SLICES in scripts/check.conf in that same change. "
                    "A non-empty PHASE_SLICES environment variable overrides that line. "
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
    return allowed, source


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


def run_fixtures() -> None:
    """Isolated copies of the four import cases. They never touch backend/."""
    global QUIET
    cases = (
        ("public api", "from ...catalog.api import published\n", None),
        ("absolute internal", "from backend.catalog.domain.item import Item\n", "F-03"),
        ("relative internal", "from ...catalog.domain.item import Item\n", "F-03"),
        ("same-slice relative", "from ..domain.item import Item\n", None),
    )
    QUIET = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            backend = Path(tmp) / "backend"
            app = backend / "practice" / "application"
            app.mkdir(parents=True)
            (backend / "catalog").mkdir()
            (backend / "practice" / "domain").mkdir(parents=True)
            for name, text, expected in cases:
                path = app / "case.py"
                path.write_text(text, encoding="utf-8")
                caught: str | None = None
                try:
                    check_file(path, backend)
                except BoundaryError as err:
                    caught = err.code
                if caught != expected:
                    QUIET = False
                    fail(
                        "F-03",
                        f"fixture {name} returned {caught}, expected {expected}.",
                        "Resolve relative imports to the same absolute module as the written-out import. "
                        "See ARCHITECTURE.md 禁止 F-03.",
                    )
    finally:
        QUIET = False
    print(
        "F-03 FIXTURE PASS: public api, absolute cross-slice, relative cross-slice, same-slice relative."
    )


def main() -> int:
    try:
        run_fixtures()
        allowed, source = scan_backend()
    except BoundaryError:
        return 1
    shown = " ".join(name for name in SLICES if name in allowed)
    print(
        "LINT PASS: dependency direction, file-size cap, and phase scope "
        f"({shown}, from {source}) hold."
    )
    return 0


def scan_backend() -> tuple[frozenset[str], str]:
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
    phase = check_phase_scope()
    check_apps_do_not_import_backend()
    return phase


if __name__ == "__main__":
    sys.exit(main())
