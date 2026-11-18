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
            self.assertEqual([event.outcome for event in logger.events], ["ok"])
            self.assertEqual(logger.events[-1].event, "log_retention_swept")

    def test_row_counts_are_logged_before_the_ok_line(self) -> None:
        from unittest import mock

        with TemporaryDirectory() as tmp:
            logger = ListLog()
            with mock.patch("backend.bootstrap.retention._purge_rows", return_value=(2, 0, 4)):
                sweep(Path(tmp), 14, 1825, "postgresql://example", logger, session_days=30, attempt_days=30)
            outcomes = [event.outcome for event in logger.events]
            self.assertEqual(outcomes, ["2", "0", "4", "ok"])
            self.assertTrue(all(event.event == "log_retention_swept" for event in logger.events))
            self.assertTrue(all(event.level == "INFO" for event in logger.events))
