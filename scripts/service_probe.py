"""Start one process, wait until it is ready, run one smoke call, then stop it.

A resident process is not waited on until it exits. When SERVICE_CMD is set,
the check starts that process after install. The probe stops the process tree it started,
including a shell wrapper and the service behind it. cleaned is true only
after those processes have exited.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProbeResult:
    status: str
    detail: str
    cleaned: bool
    returncode: int | None


class SmokeTimedOut(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def supervise(
    command: list[str] | str,
    *,
    ready_token: str,
    timeout_s: float,
    smoke: Callable[[], int],
    shell: bool = False,
    health_url: str = "",
) -> ProbeResult:
    proc = _spawn(command, shell=shell, pipe=True)
    try:
        ready = _wait_ready(proc, ready_token, timeout_s)
        if ready == "exited":
            return _finish(proc, "startup_failed", f"exited {proc.returncode} before ready", proc.returncode)
        if ready == "timeout":
            return _finish(proc, "ready_timeout", "ready wait elapsed", proc.returncode)
        if health_url:
            if proc.poll() is not None:
                return _finish(
                    proc,
                    "startup_failed",
                    f"exited {proc.returncode} after ready",
                    proc.returncode,
                )
            health = _request_health(health_url)
            if health != "ok":
                if proc.poll() is not None:
                    return _finish(
                        proc,
                        "startup_failed",
                        f"exited {proc.returncode} before health completed",
                        proc.returncode,
                    )
                return _finish(proc, "health_failed", health, None)
            if not _bound_by(proc, health_url):
                return _finish(proc, "not_bound", "the started process is not listening", None)
        try:
            smoke_code = smoke()
        except SmokeTimedOut as exc:
            return _finish(proc, "smoke_timeout", exc.detail, None)
        if smoke_code != 0:
            return _finish(proc, "smoke_failed", f"smoke exit {smoke_code}", smoke_code)
        if proc.poll() is not None:
            return _finish(
                proc,
                "startup_failed",
                f"exited {proc.returncode} before smoke finished",
                proc.returncode,
            )
        if health_url and not _bound_by(proc, health_url):
            return _finish(proc, "not_bound", "the started process stopped listening before smoke finished", None)
        return _finish(proc, "ok", "ready, smoke passed, process stopped", 0)
    finally:
        _stop(proc)


def _request_health(url: str) -> str:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            status = getattr(response, "status", 200)
            raw = response.read()
    except Exception as exc:
        return "health request failed: " + type(exc).__name__
    if status != 200:
        return "health status " + str(status)
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "health body is not json"
    if not isinstance(body, dict) or set(body) != {"status"} or body.get("status") != "ok":
        return "health body is not status ok"
    return "ok"


def _finish(proc: subprocess.Popen[str], status: str, detail: str, code: int | None) -> ProbeResult:
    cleaned = _stop(proc)
    leftovers = getattr(proc, "_probe_leftovers", [])
    if leftovers:
        detail = f"{detail}; still running: {','.join(str(pid) for pid in leftovers)}"
    failed = getattr(proc, "_probe_wait_failed", "")
    if failed:
        detail = f"{detail}; wait failed: {failed}"
    return ProbeResult(status, detail, cleaned, code)


def _wait_ready(proc: subprocess.Popen[str], token: str, timeout_s: float) -> str:
    found = threading.Event()

    def read_stdout() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            if token in line:
                found.set()
                return

    thread = threading.Thread(target=read_stdout, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if found.is_set():
            thread.join(timeout=1)
            return "ready"
        if proc.poll() is not None:
            thread.join(timeout=1)
            return "exited"
        time.sleep(0.02)
    thread.join(timeout=0.2)
    if found.is_set():
        return "ready"
    if proc.poll() is not None:
        return "exited"
    return "timeout"


def _spawn(command: list[str] | str, *, shell: bool, pipe: bool) -> subprocess.Popen[str]:
    kwargs: dict[str, object] = {"shell": shell, "text": True}
    if pipe:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flags:
            kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]


def _stop(proc: subprocess.Popen[str]) -> bool:
    tracked = getattr(proc, "_probe_pids", None)
    if tracked is None:
        # Stamp creation time before the kill. Windows can reuse a pid
        # before this poll ends, and that new process is not our leftover.
        tracked = [_stamp(pid) for pid in (proc.pid, *_descendants(proc.pid))]
        proc._probe_pids = tracked  # type: ignore[attr-defined]
    if not getattr(proc, "_probe_kill_sent", False):
        _kill_tree(proc)
        proc._probe_kill_sent = True  # type: ignore[attr-defined]
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired as stuck:
                proc._probe_wait_failed = str(stuck)  # type: ignore[attr-defined]
        stdout = proc.stdout
        if stdout is not None and hasattr(stdout, "closed") and not stdout.closed:
            stdout.close()
    deadline = time.monotonic() + 2
    leftovers: list[int] = []
    while time.monotonic() < deadline:
        leftovers = [pid for pid, started in tracked if _same_process(pid, started)]
        if not leftovers:
            break
        time.sleep(0.05)
    proc._probe_leftovers = leftovers  # type: ignore[attr-defined]
    return not leftovers


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            return


def _descendants(pid: int) -> list[int]:
    found: list[int] = []
    for child in _children(pid):
        found.append(child)
        found.extend(_descendants(child))
    return found


def _children(parent: int) -> list[int]:
    if parent <= 0:
        return []
    if sys.platform == "win32":
        return _windows_children(parent)
    return _posix_children(parent)


def _stamp(pid: int) -> tuple[int, int | None]:
    if sys.platform == "win32":
        return pid, _windows_started(pid)
    return pid, None


def _same_process(pid: int, started: int | None) -> bool:
    if not _alive(pid):
        return False
    if started is None or sys.platform != "win32":
        return True
    return _windows_started(pid) == started


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_alive(pid)
    return _posix_alive(pid)


def _windows_children(parent: int) -> list[int]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot_flag = 0x00000002
    entry_type = _process_entry()
    snap = kernel32.CreateToolhelp32Snapshot(snapshot_flag, 0)
    if snap in (0, None) or int(snap) == -1:
        return []
    entry = entry_type()
    entry.dwSize = ctypes.sizeof(entry_type)
    found: list[int] = []
    try:
        ok = kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            if int(entry.th32ParentProcessID) == parent:
                found.append(int(entry.th32ProcessID))
            ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return found


def _process_entry() -> type:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    return PROCESSENTRY32


def _windows_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    try:
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    finally:
        kernel32.CloseHandle(handle)
    return bool(ok) and code.value == 259


def _windows_started(pid: int) -> int | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    created = wintypes.FILETIME()
    exited = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    try:
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
    finally:
        kernel32.CloseHandle(handle)
    if not ok:
        return None
    return (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)


def _posix_children(parent: int) -> list[int]:
    found: list[int] = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return found
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8") as handle:
                stat = handle.read()
        except OSError:
            continue
        end = stat.rfind(")")
        parts = stat[end + 2 :].split()
        if len(parts) > 1 and parts[1] == str(parent):
            found.append(int(name))
    return found


def _posix_alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            stat = handle.read()
    except OSError:
        return False
    end = stat.rfind(")")
    parts = stat[end + 2 :].split()
    return bool(parts) and parts[0] != "Z"


def _bound_by(proc: subprocess.Popen[str], health_url: str) -> bool:
    port = _port_of(health_url)
    if port is None:
        return False
    listeners = _listening_pids(port)
    owned = {proc.pid, *_descendants(proc.pid)}
    return bool(listeners & owned)


def _port_of(url: str) -> int | None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.port:
        return int(parsed.port)
    if parsed.scheme == "http":
        return 80
    if parsed.scheme == "https":
        return 443
    return None


def _listening_pids(port: int) -> set[int]:
    if sys.platform == "win32":
        return _windows_listening_pids(port)
    return _posix_listening_pids(port)


def _windows_listening_pids(port: int) -> set[int]:
    import ctypes
    import socket
    from ctypes import wintypes

    table_owner_pid_listener = 3
    af_inet = 2
    iphlpapi = ctypes.WinDLL("iphlpapi")
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, af_inet, table_owner_pid_listener, 0)
    if size.value <= 0:
        return set()
    buf = ctypes.create_string_buffer(size.value)
    ret = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, af_inet, table_owner_pid_listener, 0)
    if ret != 0:
        return set()

    class Row(ctypes.Structure):
        _fields_ = [
            ("dwState", wintypes.DWORD),
            ("dwLocalAddr", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("dwRemoteAddr", wintypes.DWORD),
            ("dwRemotePort", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

    count = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    rows = ctypes.cast(ctypes.addressof(buf) + ctypes.sizeof(wintypes.DWORD), ctypes.POINTER(Row))
    found: set[int] = set()
    for index in range(count):
        local_port = socket.ntohs(int(rows[index].dwLocalPort) & 0xFFFF)
        if local_port == port:
            found.add(int(rows[index].dwOwningPid))
    return found


def _posix_listening_pids(port: int) -> set[int]:
    inodes: set[str] = set()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 10 or ":" not in parts[1]:
                continue
            if parts[3] != "0A":
                continue
            if int(parts[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(parts[9])
    if not inodes:
        return set()
    found: set[int] = set()
    try:
        names = os.listdir("/proc")
    except OSError:
        return found
    for name in names:
        if not name.isdigit():
            continue
        fd_dir = f"/proc/{name}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]") and target[8:-1] in inodes:
                found.add(int(name))
    return found


def _smoke_command(command: str, timeout_s: float) -> Callable[[], int]:
    def smoke() -> int:
        proc = _spawn(command, shell=True, pipe=False)
        try:
            return int(proc.wait(timeout=timeout_s))
        except subprocess.TimeoutExpired:
            _stop(proc)
            raise SmokeTimedOut(f"smoke exceeded {timeout_s}s") from None

    return smoke


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--ready-token", default="READY")
    parser.add_argument("--smoke", default="")
    parser.add_argument("--smoke-timeout", type=float, default=5)
    parser.add_argument("--health-url", default="")
    args = parser.parse_args(argv)
    if args.smoke:
        smoke = _smoke_command(args.smoke, args.smoke_timeout)
    else:
        def smoke() -> int:
            print("smoke command is empty")
            return 2

    result = supervise(
        args.command,
        ready_token=args.ready_token,
        timeout_s=args.timeout,
        smoke=smoke,
        shell=True,
        health_url=args.health_url,
    )
    print(f"{result.status} {result.detail} cleaned={result.cleaned}")
    return 0 if result.status == "ok" and result.cleaned else 1


if __name__ == "__main__":
    sys.exit(main())
