"""Synthetic process: startup failure, ready timeout, smoke failure, success, cleanup."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from scripts.service_probe import supervise

PY = sys.executable
ROOT = Path(__file__).resolve().parents[1]


def command(code: str) -> list[str]:
    return [PY, "-c", code]


class ServiceProbeTest(unittest.TestCase):
    def test_startup_failure_is_cleaned_up(self) -> None:
        result = supervise(
            command("import sys; sys.exit(3)"),
            ready_token="READY",
            timeout_s=2,
            smoke=lambda: 0,
        )
        self.assertEqual(result.status, "startup_failed")
        self.assertTrue(result.cleaned)

    def test_ready_timeout_kills_the_process(self) -> None:
        result = supervise(
            command("import time; time.sleep(30)"),
            ready_token="READY",
            timeout_s=0.4,
            smoke=lambda: 0,
        )
        self.assertEqual(result.status, "ready_timeout")
        self.assertTrue(result.cleaned)

    def test_smoke_failure_kills_the_process(self) -> None:
        result = supervise(
            command("import time; print('READY', flush=True); time.sleep(30)"),
            ready_token="READY",
            timeout_s=2,
            smoke=lambda: 1,
        )
        self.assertEqual(result.status, "smoke_failed")
        self.assertTrue(result.cleaned)
        self.assertEqual(result.returncode, 1)

    def test_success_stops_the_process(self) -> None:
        result = supervise(
            command("import time; print('READY', flush=True); time.sleep(30)"),
            ready_token="READY",
            timeout_s=2,
            smoke=lambda: 0,
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.cleaned)
        self.assertEqual(result.returncode, 0)


class ServiceProbeCommandTest(unittest.TestCase):
    def test_shell_command_is_stopped_when_the_probe_returns(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pid_path = root / "pid"
            marker = root / "late"
            script = root / "service.py"
            script.write_text(
                "import os, time\n"
                "from pathlib import Path\n"
                f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
                "print('READY', flush=True)\n"
                "time.sleep(3)\n"
                f"Path({str(marker)!r}).write_text('late')\n",
                encoding="utf-8",
            )
            command = _shell_command([PY, str(script)])
            smoke = _shell_command([PY, "-c", "import sys; sys.exit(0)"])
            completed = subprocess.run(
                [
                    PY,
                    "scripts/service_probe.py",
                    "--command",
                    command,
                    "--timeout",
                    "3",
                    "--ready-token",
                    "READY",
                    "--smoke",
                    smoke,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            pid = int(pid_path.read_text(encoding="utf-8")) if pid_path.exists() else 0
            try:
                alive_after = pid_alive(pid)
                time.sleep(3.2)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn("cleaned=True", completed.stdout)
                self.assertFalse(alive_after, completed.stdout + completed.stderr)
                self.assertFalse(marker.exists(), "the service wrote its late marker after the probe returned")
            finally:
                _kill_pid(pid)

    def test_smoke_timeout_stops_the_service_and_the_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            service_pid = root / "service.pid"
            service_marker = root / "service.late"
            smoke_pid = root / "smoke.pid"
            smoke_marker = root / "smoke.late"
            service = root / "service.py"
            smoke_script = root / "smoke.py"
            service.write_text(
                "import os, time\n"
                "from pathlib import Path\n"
                f"Path({str(service_pid)!r}).write_text(str(os.getpid()))\n"
                "print('READY', flush=True)\n"
                "time.sleep(30)\n"
                f"Path({str(service_marker)!r}).write_text('late')\n",
                encoding="utf-8",
            )
            smoke_script.write_text(
                "import os, time\n"
                "from pathlib import Path\n"
                f"Path({str(smoke_pid)!r}).write_text(str(os.getpid()))\n"
                "time.sleep(30)\n"
                f"Path({str(smoke_marker)!r}).write_text('late')\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    PY,
                    "scripts/service_probe.py",
                    "--command",
                    _shell_command([PY, str(service)]),
                    "--timeout",
                    "3",
                    "--ready-token",
                    "READY",
                    "--smoke",
                    _shell_command([PY, str(smoke_script)]),
                    "--smoke-timeout",
                    "1",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            service_id = int(service_pid.read_text(encoding="utf-8")) if service_pid.exists() else 0
            smoke_id = int(smoke_pid.read_text(encoding="utf-8")) if smoke_pid.exists() else 0
            try:
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn("smoke_timeout", completed.stdout)
                self.assertIn("smoke exceeded 1", completed.stdout)
                self.assertIn("cleaned=True", completed.stdout)
                self.assertGreater(service_id, 0)
                self.assertGreater(smoke_id, 0)
                self.assertFalse(pid_alive(service_id), completed.stdout)
                self.assertFalse(pid_alive(smoke_id), completed.stdout)
                self.assertFalse(service_marker.exists())
                self.assertFalse(smoke_marker.exists())
            finally:
                _kill_pid(service_id)
                _kill_pid(smoke_id)


class ServiceProbeHealthTest(unittest.TestCase):
    def test_exit_after_ready_fails_before_smoke(self) -> None:
        result = supervise(
            command("print('READY', flush=True)"),
            ready_token="READY",
            timeout_s=2,
            smoke=lambda: 0,
            health_url="http://127.0.0.1:9/health",
        )
        self.assertEqual(result.status, "startup_failed")
        self.assertIn("exited", result.detail)
        self.assertTrue(result.cleaned)

    def test_occupied_port_fails_and_leaves_the_holder(self) -> None:
        import socket

        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        try:
            code = (
                "import socket, sys\n"
                "sock = socket.socket()\n"
                "try:\n"
                f"    sock.bind(('127.0.0.1', {port}))\n"
                "except OSError:\n"
                "    sys.exit(4)\n"
                "print('READY', flush=True)\n"
            )
            result = supervise(
                command(code),
                ready_token="READY",
                timeout_s=2,
                smoke=lambda: 0,
            )
            self.assertEqual(result.status, "startup_failed")
            self.assertTrue(result.cleaned)
            client = socket.create_connection(("127.0.0.1", port), timeout=1)
            client.close()
        finally:
            holder.close()

    def test_health_after_ready_then_the_port_is_free(self) -> None:
        import socket

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        code = (
            "import json, threading\n"
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        body = b'{\"status\": \"ok\"}'\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type', 'application/json')\n"
            "        self.send_header('Content-Length', str(len(body)))\n"
            "        self.end_headers()\n"
            "        self.wfile.write(body)\n"
            "    def log_message(self, fmt, *args):\n"
            "        return\n"
            f"server = ThreadingHTTPServer(('127.0.0.1', {port}), Handler)\n"
            "threading.Thread(target=server.serve_forever, daemon=True).start()\n"
            "print('READY', flush=True)\n"
            "threading.Event().wait()\n"
        )
        result = supervise(
            command(code),
            ready_token="READY",
            timeout_s=3,
            smoke=lambda: 0,
            health_url=f"http://127.0.0.1:{port}/health",
        )
        self.assertEqual(result.status, "ok", result.detail)
        self.assertTrue(result.cleaned)
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)

    def test_delayed_bind_within_the_ready_budget_passes(self) -> None:
        import socket

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        code = (
            "import threading, time\n"
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "print('READY', flush=True)\n"
            "time.sleep(4)\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        body = b'{\"status\": \"ok\"}'\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type', 'application/json')\n"
            "        self.send_header('Content-Length', str(len(body)))\n"
            "        self.end_headers()\n"
            "        self.wfile.write(body)\n"
            "    def log_message(self, fmt, *args):\n"
            "        return\n"
            f"server = ThreadingHTTPServer(('127.0.0.1', {port}), Handler)\n"
            "threading.Thread(target=server.serve_forever, daemon=True).start()\n"
            "threading.Event().wait()\n"
        )
        started = time.monotonic()
        result = supervise(
            command(code),
            ready_token="READY",
            timeout_s=8,
            smoke=lambda: 0,
            health_url=f"http://127.0.0.1:{port}/health",
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.status, "ok", result.detail)
        self.assertTrue(result.cleaned)
        self.assertGreater(elapsed, 3.5, result.detail)
        self.assertLess(elapsed, 12, result.detail)
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)

    def test_health_waits_through_the_ready_budget_then_fails(self) -> None:
        started = time.monotonic()
        result = supervise(
            command("import time; print('READY', flush=True); time.sleep(30)"),
            ready_token="READY",
            timeout_s=0.8,
            smoke=lambda: 0,
            health_url="http://127.0.0.1:9/health",
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.status, "health_failed", result.detail)
        self.assertIn("ready budget elapsed", result.detail)
        self.assertTrue(result.cleaned)
        self.assertGreater(elapsed, 0.6)
        self.assertLess(elapsed, 3)

    def test_slow_health_body_past_the_ready_budget_fails(self) -> None:
        import socket

        import scripts.service_probe as probe_mod

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        budget = 1.0
        with tempfile.TemporaryDirectory() as tmp:
            stamp = Path(tmp) / "drop.txt"
            code = (
                "import socket, time\n"
                "sock = socket.socket()\n"
                f"sock.bind(('127.0.0.1', {port}))\n"
                "sock.listen(1)\n"
                "print('READY', flush=True)\n"
                "conn, _addr = sock.accept()\n"
                "body = b'{\"status\":\"ok\"}'\n"
                "crlf = chr(13) + chr(10)\n"
                "first = ('HTTP/1.1 200 OK' + crlf + 'Content-Type: application/json' + crlf).encode('ascii')\n"
                "rest = ('Content-Length: %d' % len(body) + crlf + 'Connection: close' + crlf + crlf).encode('ascii')\n"
                f"path = {stamp.as_posix()!r}\n"
                "sent = 0\n"
                "dropped = ''\n"
                "try:\n"
                "    conn.sendall(first)\n"
                "    time.sleep(0.25)\n"
                "    conn.sendall(rest)\n"
                "    for piece in body:\n"
                "        time.sleep(0.2)\n"
                "        with open(path, 'w', encoding='utf-8') as handle:\n"
                "            handle.write('%s %s' % (time.time(), sent))\n"
                "        conn.sendall(bytes([piece]))\n"
                "        sent += 1\n"
                "except OSError as exc:\n"
                "    dropped = type(exc).__name__\n"
                "with open(path, 'w', encoding='utf-8') as handle:\n"
                "    handle.write('%s %s %s' % (time.time(), sent, dropped))\n"
                "time.sleep(30)\n"
            )
            marks: dict[str, float] = {}
            original = probe_mod._finish

            def wrapped(proc: subprocess.Popen[str], status: str, detail: str, code: int | None) -> probe_mod.ProbeResult:
                marks["judged"] = time.time()
                return original(proc, status, detail, code)

            probe_mod._finish = wrapped
            started = time.time()
            try:
                result = supervise(
                    command(code),
                    ready_token="READY",
                    timeout_s=budget,
                    smoke=lambda: 0,
                    health_url=f"http://127.0.0.1:{port}/health",
                )
            finally:
                probe_mod._finish = original
            finished = time.time()
            judged = marks["judged"] - started
            cleaned_at = finished - started
            progress = stamp.read_text(encoding="utf-8") if stamp.exists() else ""
            sent = int(progress.split()[1]) if len(progress.split()) >= 2 else -1
            print(
                f"SLOW_HEALTH budget={budget:.1f} judged={judged:.3f} "
                f"cleaned={cleaned_at:.3f} status={result.status} sent={sent} detail={result.detail}"
            )
            self.assertEqual(result.status, "health_failed", result.detail)
            self.assertIn("ready budget elapsed", result.detail)
            self.assertNotIn("status=ok", result.detail)
            self.assertTrue(result.cleaned)
            self.assertGreater(judged, 0.7, result.detail)
            self.assertLess(judged, 1.8, result.detail)
            self.assertGreaterEqual(cleaned_at, judged)
            self.assertLess(cleaned_at, 2.2, result.detail)
            self.assertGreaterEqual(sent, 0)
            self.assertLess(sent, len(b'{"status":"ok"}'))
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", port), timeout=1)

    def test_exit_while_waiting_for_bind_fails_promptly(self) -> None:
        started = time.monotonic()
        result = supervise(
            command("import time; print('READY', flush=True); time.sleep(0.15); raise SystemExit(7)"),
            ready_token="READY",
            timeout_s=8,
            smoke=lambda: 0,
            health_url="http://127.0.0.1:9/health",
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.status, "startup_failed", result.detail)
        self.assertIn("exited", result.detail)
        self.assertTrue(result.cleaned)
        self.assertLess(elapsed, 3, result.detail)


class ServiceProbeRealEntryTest(unittest.TestCase):
    def test_exit_during_smoke_is_not_success(self) -> None:
        def smoke() -> int:
            time.sleep(0.3)
            return 0

        result = supervise(
            command("print('READY', flush=True)"),
            ready_token="READY",
            timeout_s=2,
            smoke=smoke,
        )
        self.assertEqual(result.status, "startup_failed")
        self.assertIn("before smoke finished", result.detail)
        self.assertTrue(result.cleaned)

    def test_health_from_another_process_is_not_our_bind(self) -> None:
        import socket
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: object) -> None:
                return

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        holder = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        thread = threading.Thread(target=holder.serve_forever, daemon=True)
        thread.start()
        try:
            result = supervise(
                command("import time; print('READY', flush=True); time.sleep(30)"),
                ready_token="READY",
                timeout_s=2,
                smoke=lambda: 0,
                health_url=f"http://127.0.0.1:{port}/health",
            )
            self.assertEqual(result.status, "not_bound", result.detail)
            self.assertTrue(result.cleaned)
            client = socket.create_connection(("127.0.0.1", port), timeout=1)
            client.close()
        finally:
            holder.shutdown()
            holder.server_close()

    def test_cli_nonzero_when_the_service_exits_early(self) -> None:
        completed = subprocess.run(
            [
                PY,
                "scripts/service_probe.py",
                "--command",
                _shell_command([PY, "-c", "print('READY', flush=True)"]),
                "--timeout",
                "3",
                "--ready-token",
                "READY",
                "--smoke",
                _shell_command([PY, "-c", "import time; time.sleep(0.3)"]),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("startup_failed", completed.stdout)

    def test_real_uvicorn_leaves_the_port_holder_when_bind_fails(self) -> None:
        import socket
        import threading

        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        # Uvicorn prints its ready line before bind. The probe then connects
        # to the health URL, so this occupant has to accept that connection.
        # A one-slot backlog with no accept leaves the next connect waiting.
        holder.listen(8)
        port = holder.getsockname()[1]
        stop = threading.Event()

        def accept_until_stopped() -> None:
            holder.settimeout(0.2)
            while not stop.is_set():
                try:
                    client, _addr = holder.accept()
                except OSError:
                    continue
                client.close()

        thread = threading.Thread(target=accept_until_stopped, daemon=True)
        thread.start()
        command = _shell_command(
            [
                PY,
                "-m",
                "uvicorn",
                "backend.bootstrap.http_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ]
        )
        try:
            completed = subprocess.run(
                [
                    PY,
                    "scripts/service_probe.py",
                    "--command",
                    command,
                    "--timeout",
                    "20",
                    "--ready-token",
                    "Application startup complete",
                    "--smoke",
                    _shell_command([PY, "-c", "import sys; raise SystemExit(0)"]),
                    "--health-url",
                    f"http://127.0.0.1:{port}/health",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=40,
            )
            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue(
                any(token in completed.stdout for token in ("startup_failed", "not_bound", "health_failed")),
                completed.stdout + completed.stderr,
            )
            client = socket.create_connection(("127.0.0.1", port), timeout=1)
            client.close()
        finally:
            stop.set()
            holder.close()


class ServiceProbeImportTest(unittest.TestCase):
    def test_module_imports_as_a_script(self) -> None:
        completed = subprocess.run(
            [PY, "scripts/service_probe.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


def _shell_command(args: list[str]) -> str:
    if sys.platform == "win32":
        return subprocess.list2cmdline(args)
    import shlex

    return shlex.join(args)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return code.value == 259
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        stat = stat_path.read_text(encoding="utf-8")
    except OSError:
        return False
    end = stat.rfind(")")
    parts = stat[end + 2 :].split()
    return bool(parts) and parts[0] != "Z"


def _kill_pid(pid: int) -> None:
    if pid <= 0 or not pid_alive(pid):
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        return
    try:
        os.kill(pid, 9)
    except OSError:
        return


if __name__ == "__main__":
    unittest.main()
