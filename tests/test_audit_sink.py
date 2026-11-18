"""Audit sink failure keeps the event and reports it on the runtime stream."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.bootstrap.audit_pg import AuditPg
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import CompositeLogger


class ListLog:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class BrokenPool:
    def connection(self) -> object:
        raise RuntimeError("database down")


class AuditSinkTest(unittest.TestCase):
    def test_failed_insert_writes_fallback_and_runtime_error(self) -> None:
        runtime = ListLog()
        with TemporaryDirectory() as tmp:
            fallback = Path(tmp) / "audit-fallback.jsonl"
            sink = AuditPg(BrokenPool(), runtime, fallback)
            logger = CompositeLogger([runtime], sink)
            logger.log(
                LogEvent(
                    time="2026-11-18T00:00:00Z",
                    level="INFO",
                    event="admin_action_committed",
                    request_id="req-audit",
                    module="identity.login",
                    outcome="ok",
                    duration_ms=1,
                    actor_user_id="user-1",
                    target_kind="user",
                    target_id="user-1",
                    audit=True,
                )
            )
            self.assertTrue(fallback.is_file())
            saved = json.loads(fallback.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(saved["event"], "admin_action_committed")
            self.assertEqual(saved["actor_user_id"], "user-1")
            self.assertTrue(saved["audit"])
        self.assertEqual(runtime.events[-1].event, "audit_write_failed")
        self.assertEqual(runtime.events[-1].request_id, "req-audit")
