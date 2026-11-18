"""The error webhook posts five fields and does not block the caller."""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

from backend.bootstrap.error_ring import ErrorRing
from backend.kernel.log_event import LogEvent


class _Hook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        delay = float(getattr(self.server, "delay", 0))
        if delay:
            time.sleep(delay)
        self.server.received.append(raw)  # type: ignore[attr-defined]
        self.server.hits += 1  # type: ignore[attr-defined]
        failed = int(getattr(self.server, "fail_times", 0))
        code = 500 if self.server.hits <= failed else 204  # type: ignore[attr-defined]
        self.send_response(code)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


class ErrorWebhookTest(unittest.TestCase):
    def test_one_post_contains_only_the_five_fields(self) -> None:
        server = _listen()
        try:
            ring = ErrorRing(url=_url(server))
            ring.add(_error())
            ring.wait()
            self.assertEqual(server.hits, 1)
            body = json.loads(server.received[0].decode("utf-8"))
        finally:
            _stop(server)
        self.assertEqual(
            set(body),
            {"time", "request_id", "module", "event", "outcome"},
        )
        self.assertEqual(body["request_id"], "req-webhook-1")
        self.assertEqual(body["module"], "practice")
        self.assertEqual(body["event"], "use_case_failed")
        self.assertEqual(body["outcome"], "store_failed")
        self.assertNotIn("teacher-synth", json.dumps(body))
        self.assertNotIn("duration_ms", body)

    def test_a_slow_receiver_does_not_block_add(self) -> None:
        server = _listen(delay=1)
        try:
            ring = ErrorRing(url=_url(server))
            started = time.perf_counter()
            ring.add(_error())
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.4)
            ring.wait()
            self.assertEqual(server.hits, 1)
        finally:
            _stop(server)

    def test_failure_retries_once_then_warns_without_a_second_error(self) -> None:
        server = _listen(fail_times=2)
        buffer = StringIO()
        try:
            ring = ErrorRing(url=_url(server))
            with redirect_stdout(buffer):
                ring.add(_error())
                ring.wait()
            self.assertEqual(server.hits, 2)
            self.assertEqual(len(ring.rows), 1)
        finally:
            _stop(server)
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        warn = json.loads(lines[0])
        self.assertEqual(warn["level"], "WARN")
        self.assertEqual(warn["event"], "webhook_failed")
        self.assertEqual(warn["outcome"], "gave_up")
        self.assertEqual(warn["request_id"], "req-webhook-1")
        self.assertNotIn(_url(server), lines[0])

    def test_one_retry_can_succeed_without_a_warn(self) -> None:
        server = _listen(fail_times=1)
        buffer = StringIO()
        try:
            ring = ErrorRing(url=_url(server))
            with redirect_stdout(buffer):
                ring.add(_error())
                ring.wait()
            self.assertEqual(server.hits, 2)
        finally:
            _stop(server)
        self.assertNotIn("webhook_failed", buffer.getvalue())

    def test_empty_url_and_non_errors_do_not_post(self) -> None:
        server = _listen()
        try:
            with mock.patch.dict(os.environ, {"K12_ERROR_WEBHOOK_URL": _url(server)}):
                quiet = ErrorRing(url="  ")
                quiet.add(_error())
                quiet.wait(0.2)
            ring = ErrorRing(url=_url(server))
            ring.add(_event("INFO", False))
            ring.add(_event("ERROR", True))
            ring.wait(0.2)
            self.assertEqual(server.hits, 0)
        finally:
            _stop(server)


def _listen(delay: float = 0, fail_times: int = 0) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Hook)
    server.received = []  # type: ignore[attr-defined]
    server.hits = 0  # type: ignore[attr-defined]
    server.delay = delay  # type: ignore[attr-defined]
    server.fail_times = fail_times  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.thread = thread  # type: ignore[attr-defined]
    thread.start()
    return server


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.thread.join(2)  # type: ignore[attr-defined]
    server.server_close()


def _url(server: ThreadingHTTPServer) -> str:
    port = server.server_address[1]
    return "http://127.0.0.1:" + str(port) + "/hook"


def _error() -> LogEvent:
    return _event("ERROR", False)


def _event(level: str, audit: bool) -> LogEvent:
    return LogEvent(
        time="2026-11-19T00:00:00Z",
        level=level,
        event="use_case_failed",
        request_id="req-webhook-1",
        module="practice",
        outcome="store_failed",
        duration_ms=3,
        actor_user_id="teacher-synth",
        audit=audit,
        detail="not-for-the-hook",
    )
