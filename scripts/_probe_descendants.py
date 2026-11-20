"""Descendant walk for the service probe.

Windows refuses a child whose start time is unknown or earlier than the root.
POSIX keeps the existing parent-pointer walk.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_LOG_DIR = Path("var")


def _service_probe():
    try:
        from scripts import service_probe as probe
    except ImportError:
        import service_probe as probe
    return probe


def _write_no_root_start_log(root_pid: int) -> None:
    try:
        directory = _service_probe()._LOG_DIR
        directory.mkdir(parents=True, exist_ok=True)
        millis = int(time.time() * 1000) % 1000
        stamp = time.strftime("%Y-%m-%dT%H-%M-%S") + f"-{millis:03d}"
        path = directory / f"probe-descendants-no-root-start-{stamp}-{root_pid}.log"
        path.write_text(
            f"root_pid={root_pid}\nreason=windows_started returned None\n",
            encoding="utf-8",
        )
    except Exception:
        return


def _posix_walk(pid: int) -> list[int]:
    found: list[int] = []
    for child in _service_probe()._children(pid):
        found.append(child)
        found.extend(_posix_walk(child))
    return found


def _descendants(root_pid: int) -> list[int]:
    if sys.platform != "win32":
        return _posix_walk(root_pid)
    probe = _service_probe()
    root_started = probe._windows_started(root_pid)
    if root_started is None:
        _write_no_root_start_log(root_pid)
        return []
    found: list[int] = []
    stack = [root_pid]
    seen = {root_pid}
    while stack:
        parent = stack.pop()
        for pid in probe._windows_children(parent):
            if pid in seen:
                continue
            child_started = probe._windows_started(pid)
            if child_started is None:
                # 无法验证，拒收。宁可漏杀，不可错杀无关进程。
                continue
            if child_started < root_started:
                continue
            found.append(pid)
            seen.add(pid)
            stack.append(pid)
    return found
