"""Own unexpired sessions. The read does not write an audit row."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from backend.identity.api import Actor
from backend.identity.application.sessions import list_own_sessions
from backend.identity.domain.records import Session, User
from backend.kernel.result import Ok

_WORLD_PATH = Path(__file__).with_name("world.py")
_SPEC = importlib.util.spec_from_file_location("k12_identity_world_own_sessions", _WORLD_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("missing identity world helper")
_WORLD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _WORLD
_SPEC.loader.exec_module(_WORLD)
memory_world = _WORLD.memory_world
pg_world = _WORLD.pg_world


class OwnSessionCases:
    def test_list_returns_unexpired_rows_newest_first(self) -> None:
        now = self.world.clock.now()
        self._user("user-1", "teacher.one")
        self._user("user-2", "teacher.two")
        self._put("older", "user-1", last_seen=now - timedelta(minutes=2), expires_at=now + timedelta(hours=2), ip_hash="abc")
        self._put(
            "newer",
            "user-1",
            last_seen=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=2),
            ip_hash="abcdef0123456789",
        )
        self._put("expired", "user-1", last_seen=now, expires_at=now - timedelta(minutes=1))
        self._put(
            "revoked",
            "user-1",
            last_seen=now,
            expires_at=now + timedelta(hours=2),
            revoked_at=now - timedelta(minutes=1),
        )
        self._put("other", "user-2", last_seen=now, expires_at=now + timedelta(hours=2))
        found: dict[str, object] = {}

        def work(db: object) -> Ok[object]:
            found["rows"] = db.sessions.list_unexpired("user-1", now)  # type: ignore[attr-defined]
            return Ok(found["rows"])

        result = self.world.run(work)
        self.assertIsInstance(result, Ok)
        rows = found["rows"]
        self.assertEqual([row.session_id for row in rows], ["newer", "older"])  # type: ignore[attr-defined]
        self.assertEqual(rows[0].ip_hash, "abcdef0123456789")  # type: ignore[index]
        self.assertEqual(rows[1].ip_hash, "abc")  # type: ignore[index]

    def test_the_use_case_does_not_write_an_audit_row(self) -> None:
        actor = Actor("user-1", "teacher", "teacher.one")
        before = self.world.audit_count()
        result = self.world.run(lambda db: list_own_sessions(db, actor, self.world.deps))
        self.assertIsInstance(result, Ok)
        self.assertEqual(result.value, ())  # type: ignore[attr-defined]
        self.assertEqual(self.world.audit_count(), before)

    def _user(self, user_id: str, username: str) -> None:
        now = self.world.clock.now()
        user = User(
            user_id=user_id,
            username=username,
            role="teacher",
            status="active",
            password_hash="v1:unused",
            password_algo="test",
            created_at=now,
            updated_at=now,
        )

        def work(db: object) -> Ok[None]:
            db.users.insert(user)  # type: ignore[attr-defined]
            return Ok(None)

        result = self.world.run(work)
        self.assertIsInstance(result, Ok)

    def _put(
        self,
        session_id: str,
        user_id: str,
        *,
        last_seen: object,
        expires_at: object,
        revoked_at: object | None = None,
        ip_hash: str = "abcdef0123456789",
    ) -> None:
        now = self.world.clock.now()
        row = Session(
            session_id=session_id,
            user_id=user_id,
            csrf_token="csrf-test",
            issued_at=now - timedelta(minutes=10),
            last_seen_at=last_seen,  # type: ignore[arg-type]
            expires_at=expires_at,  # type: ignore[arg-type]
            revoked_at=revoked_at,  # type: ignore[arg-type]
            ip_hash=ip_hash,
        )

        def work(db: object) -> Ok[None]:
            db.sessions.put(row)  # type: ignore[attr-defined]
            return Ok(None)

        result = self.world.run(work)
        self.assertIsInstance(result, Ok)


class MemoryOwnSessionTest(OwnSessionCases, unittest.TestCase):
    def setUp(self) -> None:
        self.world = memory_world()


class PgOwnSessionTest(OwnSessionCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN"):
            self.skipTest("K12_PG_DSN is not set")
        self.world = pg_world()
