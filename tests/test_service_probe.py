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
