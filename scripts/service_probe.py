"""Start one process, wait until it is ready, run one smoke call, then stop it.

A resident process is not waited on until it exits. When SERVICE_CMD is set,
the check starts that process after install. The ready token can arrive before
the port is bound. The same ready budget then keeps asking for health until
this process is bound and the body is status ok, the process exits, or the
budget ends. Connecting and reading that body share one deadline. A body that
is still arriving after the budget is a ready failure. Chunked and
Content-Length bodies are both accepted. Only an http URL is requested; any
other scheme is refused before a connection. The probe stops the
process tree it started, including a shell wrapper and the service behind it. cleaned is true only after those processes
have exited.
"""

from __future__ import annotations

import argparse
import io
import os
import signal
import socket
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
        deadline = time.monotonic() + timeout_s
        ready = _wait_ready(proc, ready_token, deadline)
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
            health = _wait_health(proc, health_url, deadline)
            if health == "exited":
                return _finish(
                    proc,
                    "startup_failed",
                    f"exited {proc.returncode} before health completed",
                    proc.returncode,
                )
            if health == "not_bound":
                return _finish(proc, "not_bound", "the started process is not listening", None)
            if health != "ok":
                return _finish(proc, "health_failed", health, None)
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


def _request_health(url: str, timeout: float = 0.4, deadline: float | None = None) -> str:
    import json
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "health url is invalid"
    if parts.scheme != "http":
        return "health url scheme is not http"
    if deadline is None:
        deadline = time.monotonic() + max(0.0, timeout)
    if time.monotonic() >= deadline:
        return "health request failed: TimeoutError"
    host = parts.hostname or "127.0.0.1"
    if port is None:
        port = 80
    path = parts.path or "/"
    if parts.query:
        path = path + "?" + parts.query
    remaining = deadline - time.monotonic()
    sock: socket.socket | None = None
    try:
        if remaining <= 0:
            return "health request failed: TimeoutError"
        sock = socket.create_connection((host, port), timeout=min(timeout, remaining))
        left = deadline - time.monotonic()
        if left <= 0:
            return "health request failed: TimeoutError"
        sock.settimeout(min(timeout, left))
        host_header = host if port in (80, 443) else f"{host}:{port}"
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host_header}\r\n"
            "Connection: close\r\nAccept: application/json\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        message = _read_http_message(sock, deadline, timeout)
        if message is None or time.monotonic() >= deadline:
            return "health request failed: TimeoutError"
    except (TimeoutError, socket.timeout):
        return "health request failed: TimeoutError"
    except Exception as exc:
        return "health request failed: " + type(exc).__name__
    finally:
        if sock is not None:
            sock.close()
    status, raw = message
    if time.monotonic() >= deadline:
        return "health request failed: TimeoutError"
    if status != 200:
        return "health status " + str(status)
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "health body is not json"
    if not isinstance(body, dict) or set(body) != {"status"} or body.get("status") != "ok":
        return "health body is not status ok"
    if time.monotonic() >= deadline:
        return "health request failed: TimeoutError"
    return "ok"


class _BudgetSocket:
    """Socket view whose reads stop at the ready deadline. The real socket stays open."""

    def __init__(self, sock: socket.socket, deadline: float, timeout: float) -> None:
        self._sock = sock
        self._deadline = deadline
        self._timeout = timeout
        self._io_refs = 0

    def recv_into(self, buffer: object, nbytes: int = 0, flags: int = 0) -> int:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError
        self._sock.settimeout(min(self._timeout, left))
        if nbytes and flags:
            return self._sock.recv_into(buffer, nbytes, flags)
        if nbytes:
            return self._sock.recv_into(buffer, nbytes)
        return self._sock.recv_into(buffer)

    def fileno(self) -> int:
        return self._sock.fileno()

    def settimeout(self, value: float | None) -> None:
        self._sock.settimeout(value)

    def _decref_socketios(self) -> None:
        if self._io_refs > 0:
            self._io_refs -= 1

    def makefile(
        self,
        mode: str = "r",
        buffering: int | None = None,
        *,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> io.BufferedReader:
        del mode, encoding, errors, newline
        raw = socket.SocketIO(self, "r")
        size = io.DEFAULT_BUFFER_SIZE if buffering is None or buffering < 0 else buffering
        return io.BufferedReader(raw, size)


def _read_http_message(
    sock: socket.socket,
    deadline: float,
    timeout: float,
) -> tuple[int, bytes] | None:
    import http.client

    response = http.client.HTTPResponse(_BudgetSocket(sock, deadline, timeout))
    left = deadline - time.monotonic()
    if left <= 0:
        return None
    sock.settimeout(min(timeout, left))
    try:
        response.begin()
    except (TimeoutError, socket.timeout):
        return None
    if time.monotonic() >= deadline:
        return None
    parts: list[bytes] = []
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        sock.settimeout(min(timeout, left))
        try:
            block = response.read(4096)
        except (TimeoutError, socket.timeout):
            return None
        if time.monotonic() >= deadline:
            return None
        if not block:
            break
        parts.append(block)
    return response.status, b"".join(parts)


def _finish(proc: subprocess.Popen[str], status: str, detail: str, code: int | None) -> ProbeResult:
    cleaned = _stop(proc)
    leftovers = getattr(proc, "_probe_leftovers", [])
    if leftovers:
        detail = f"{detail}; still running: {','.join(str(pid) for pid in leftovers)}"
    failed = getattr(proc, "_probe_wait_failed", "")
    if failed:
        detail = f"{detail}; wait failed: {failed}"
    return ProbeResult(status, detail, cleaned, code)


def _wait_health(proc: subprocess.Popen[str], url: str, deadline: float) -> str:
    last = "health request failed: waiting"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return "exited"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        health = _request_health(url, timeout=min(0.4, remaining), deadline=deadline)
        if health in ("health url scheme is not http", "health url is invalid"):
            return health
        if proc.poll() is not None:
            return "exited"
        if time.monotonic() >= deadline:
            if not str(health).startswith("health request failed"):
                health = "health request failed: TimeoutError"
            last = health
            break
        if health == "ok":
            if _bound_by(proc, url):
                return "ok"
            return "not_bound"
        if not health.startswith("health request failed"):
            if _bound_by(proc, url):
                return health
            return "not_bound"
        last = health
        pause = min(0.05, max(0.0, deadline - time.monotonic()))
        if pause:
            time.sleep(pause)
    return last + "; ready budget elapsed"


def _wait_ready(proc: subprocess.Popen[str], token: str, deadline: float) -> str:
    found = threading.Event()

    def read_stdout() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            if token in line:
                found.set()
                # Keep reading. A full pipe blocks the server on Windows.

    thread = threading.Thread(target=read_stdout, daemon=True)
    thread.start()
    while time.monotonic() < deadline:
        if found.is_set():
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
    entered = time.monotonic()
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
    if leftovers:
        _record_leftovers(proc, list(tracked), leftovers, entered)
    return not leftovers


def _record_leftovers(
    proc: subprocess.Popen[str],
    tracked: list[tuple[int, int | None]],
    leftovers: list[int],
    entered: float,
) -> None:
    try:
        _write_leftover_file(proc, tracked, leftovers, entered)
    except Exception as exc:
        try:
            _leftover_log_path(proc.pid).write_text(
                f"diagnostic error: {exc!r}\n", encoding="utf-8"
            )
        except Exception:
            return


def _write_leftover_file(
    proc: subprocess.Popen[str],
    tracked: list[tuple[int, int | None]],
    leftovers: list[int],
    entered: float,
) -> None:
    elapsed = time.monotonic() - entered
    polled = proc.poll()
    lines = [
        "# popen",
        f"proc.pid: {proc.pid}",
        f"proc.poll: {polled!r}",
        f"proc.returncode: {proc.returncode!r}",
        f"_probe_wait_failed: {getattr(proc, '_probe_wait_failed', None)!r}",
        f"_probe_kill_sent: {getattr(proc, '_probe_kill_sent', False)!r}",
        f"elapsed_s: {elapsed:.3f}",
        "",
        "# tracked",
    ]
    for pid, started in tracked:
        lines.append(f"pid: {pid} started: {started!r} is_proc: {pid == proc.pid}")
    lines.extend(["", "# leftovers"])
    stamped = {pid: started for pid, started in tracked}
    for pid in leftovers:
        lines.extend(_leftover_pid_lines(pid, stamped.get(pid)))
    _leftover_log_path(proc.pid).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _leftover_log_path(pid: int):
    from pathlib import Path

    millis = int(time.time() * 1000) % 1000
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S") + f"-{millis:03d}"
    directory = Path("var")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"probe-stop-leftovers-{stamp}-{pid}.log"


def _leftover_pid_lines(pid: int, stamped_started: int | None) -> list[str]:
    if sys.platform == "win32":
        started_now = _windows_started(pid)
        alive_now = _windows_alive(pid)
        cim = _cim_process(pid)
    else:
        started_now = None
        alive_now = False
        cim = "cim skipped: not windows"
    return [
        f"pid: {pid}",
        f"started_now: {started_now!r}",
        f"stamped_started: {stamped_started!r}",
        f"started_matches: {started_now == stamped_started}",
        f"alive_now: {alive_now}",
        "cim:",
        cim,
        "",
    ]


def _cim_process(pid: int) -> str:
    # pid is coerced to int so the WQL filter cannot carry extra PowerShell.
    safe_pid = int(pid)
    command = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new($false); "
        "Get-CimInstance Win32_Process -Filter "
        f"'ProcessId = {safe_pid}' | "
        "Select-Object ProcessId,Name,ParentProcessId,CreationDate,HandleCount,ThreadCount | "
        "Format-List"
    )
    try:
        done = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-NoLogo", "-Command", command,
            ],
            timeout=3,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "cim timeout"
    except Exception as exc:
        return f"cim error: {exc!r}"
    if not (done.stdout or "").strip():
        return "cim empty"
    return done.stdout.rstrip()


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
    return [pid for pid, ppid in _enumerate_pids(parent) if ppid == parent]


def _enumerate_pids(parent: int) -> list[tuple[int, int]]:
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    entry_type = _process_entry()
    snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap in (0, None) or int(snap) == -1:
        return []
    entry = entry_type()
    entry.dwSize = ctypes.sizeof(entry_type)
    rows: list[tuple[int, int]] = []
    try:
        ok = kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            rows.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID)))
            ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return rows


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
