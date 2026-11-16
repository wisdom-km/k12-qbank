"""Synthetic process: startup failure, ready timeout, smoke failure, success, cleanup."""

from __future__ import annotations

import subprocess
import sys
import unittest

from scripts.service_probe import supervise

PY = sys.executable


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


class ServiceProbeImportTest(unittest.TestCase):
    def test_module_imports_as_a_script(self) -> None:
        completed = subprocess.run(
            [PY, "scripts/service_probe.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
