"""Start one process, wait until it is ready, run one smoke call, then stop it.

A resident process is not waited on until it exits. SERVICE_CMD stays empty
until an HTTP process exists. Tests drive this with a short synthetic process.
"""

from __future__ import annotations

import argparse
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


def supervise(
    command: list[str] | str,
    *,
    ready_token: str,
    timeout_s: float,
    smoke: Callable[[], int],
    shell: bool = False,
) -> ProbeResult:
    proc = subprocess.Popen(
        command,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ready = _wait_ready(proc, ready_token, timeout_s)
        if ready == "exited":
            _stop(proc)
            code = proc.returncode
            return ProbeResult("startup_failed", f"exited {code} before ready", _dead(proc), code)
        if ready == "timeout":
            _stop(proc)
            return ProbeResult("ready_timeout", "ready wait elapsed", _dead(proc), proc.returncode)
        smoke_code = smoke()
        if smoke_code != 0:
            _stop(proc)
            return ProbeResult("smoke_failed", f"smoke exit {smoke_code}", _dead(proc), smoke_code)
        _stop(proc)
        return ProbeResult("ok", "ready, smoke passed, process stopped", _dead(proc), 0)
    finally:
        _stop(proc)


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


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    stdout = proc.stdout
    if stdout is not None and not stdout.closed:
        stdout.close()


def _dead(proc: subprocess.Popen[str]) -> bool:
    return proc.poll() is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--ready-token", default="READY")
    parser.add_argument("--smoke", default="")
    args = parser.parse_args(argv)
    if args.smoke:
        def smoke() -> int:
            completed = subprocess.run(args.smoke, shell=True, check=False)
            return int(completed.returncode)
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
    )
    print(f"{result.status} {result.detail} cleaned={result.cleaned}")
    return 0 if result.status == "ok" and result.cleaned else 1


if __name__ == "__main__":
    sys.exit(main())
