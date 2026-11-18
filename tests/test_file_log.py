"""File sink rotation and retention."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.bootstrap.file_log import MAX_BYTES, FileLog
from backend.kernel.log_event import LogEvent


def _event(name: str = "http_completed") -> LogEvent:
    return LogEvent(
        time="2026-11-18T00:00:00Z",
        level="INFO",
        event=name,
        request_id="req-log",
        module="file_log",
        outcome="ok",
        duration_ms=1,
    )


class FileLogTest(unittest.TestCase):
    def test_default_cap_is_50mb(self) -> None:
        self.assertEqual(MAX_BYTES, 50 * 1024 * 1024)

    def test_rotates_when_the_next_line_crosses_the_cap(self) -> None:
        clock = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmp:
            sink = FileLog(Path(tmp), max_bytes=64, clock=lambda: clock)
            first = sink._active()
            first.write_bytes(b"x" * 60)
            sink.log(_event())
            rotated = list(Path(tmp).glob("runtime-20261118-*.jsonl"))
            self.assertEqual(len(rotated), 1)
            active = sink._active().read_text(encoding="utf-8")
            names = [json.loads(line)["event"] for line in active.splitlines()]
            self.assertEqual(names[0], "log_rotation")
            self.assertIn("http_completed", names)

    def test_purges_files_older_than_the_retain_window(self) -> None:
        now = datetime(2026, 11, 18, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmp:
            old = Path(tmp) / "runtime-20200101.jsonl"
            old.write_text("{}\n", encoding="utf-8")
            ago = (now - timedelta(days=30)).timestamp()
            os.utime(old, (ago, ago))
            sink = FileLog(Path(tmp), retain_days=14, clock=lambda: now)
            sink.log(_event("app_started"))
            self.assertFalse(old.exists())
            self.assertTrue(sink._active().exists())
