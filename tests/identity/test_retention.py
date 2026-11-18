"""Expired runtime files are removed and the sweep is logged."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.bootstrap.retention import sweep
from backend.kernel.log_event import LogEvent


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class RetentionSweepTest(unittest.TestCase):
    def test_old_runtime_file_is_removed(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = folder / "runtime-20200101.jsonl"
            recent = folder / "runtime-20261118.jsonl"
            old.write_text("{}\n", encoding="utf-8")
            recent.write_text("{}\n", encoding="utf-8")
            stamp = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
            os.utime(old, (stamp, stamp))
            logger = ListLog()
            removed = sweep(folder, 14, 1825, "", logger)
            self.assertGreaterEqual(removed, 1)
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertEqual(logger.events[-1].event, "log_retention_swept")
            self.assertEqual(logger.events[-1].outcome, "ok")
