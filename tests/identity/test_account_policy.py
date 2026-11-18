"""Bootstrap password flag, read-audit detail, and the last active admin."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from backend.identity.api import Actor, LoginCommand
from backend.identity.application.bootstrap_admin import bootstrap_admin
from backend.identity.application.login import load_session, login
from backend.identity.application.passwords import change_own_password, reset_teacher_password
from backend.identity.application.queries import list_audit_events, list_recent_errors
from backend.identity.application.roles import change_role, disable_user
from backend.identity.application.teachers import create_teacher, disable_teacher
from backend.identity.domain.digest import digest
from backend.identity.domain.records import Session
from backend.kernel.result import Err, Ok

_WORLD_PATH = Path(__file__).with_name("world.py")
_SPEC = importlib.util.spec_from_file_location("k12_identity_world_account", _WORLD_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("missing identity world helper")
_WORLD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _WORLD
_SPEC.loader.exec_module(_WORLD)
World = _WORLD.World
memory_world = _WORLD.memory_world
pg_world = _WORLD.pg_world

ADMIN_SECRET = "admin-pass1"
TEACH_SECRET = "teach-pass1"
NEXT_SECRET = "new-pass123"
NEEDLE = "needle-value"


class AccountCases:
    world: World

    def test_bootstrap_must_change_and_a_created_teacher_does_not(self) -> None:
        admin = self._boot()
        self.assertTrue(self._user(admin.user_id).must_change_password)  # type: ignore[attr-defined]
        teacher = self._teacher("teacher.one")
        self.assertFalse(teacher.must_change_password)  # type: ignore[attr-defined]

    def test_only_a_successful_change_clears_the_flag(self) -> None:
        admin = self._boot()
        weak = self.world.run(
            lambda db: change_own_password(db, admin, ADMIN_SECRET, "short", self.world.deps, "weak")
        )
        self.assertEqual(weak.code, "weak_password")  # type: ignore[attr-defined]
        bad = self.world.run(
            lambda db: change_own_password(db, admin, "wrong-pass1", NEXT_SECRET, self.world.deps, "bad")
        )
        self.assertEqual(bad.code, "invalid_credentials")  # type: ignore[attr-defined]
        self.assertTrue(self._user(admin.user_id).must_change_password)  # type: ignore[attr-defined]

        def rewrite(db: object) -> Ok[None]:
            db.users.update_password(admin.user_id, "v1:" + ADMIN_SECRET, "argon2id", self.world.clock.now())  # type: ignore[attr-defined]
            return Ok(None)

        self.world.run(rewrite)
        self.assertTrue(self._user(admin.user_id).must_change_password)  # type: ignore[attr-defined]
        signed = self._login("admin", ADMIN_SECRET)
        changed = self.world.run(
            lambda db: change_own_password(db, admin, ADMIN_SECRET, NEXT_SECRET, self.world.deps, "pw")
        )
        self.assertIsInstance(changed, Ok)
        self.assertFalse(self._user(admin.user_id).must_change_password)  # type: ignore[attr-defined]
        loaded = self.world.run(lambda db: Ok(load_session(db, signed.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNotNone(loaded.value)

    def test_last_active_admin_cannot_be_removed(self) -> None:
        admin = self._boot()
        refused = self._disable(admin, admin.user_id)
        self.assertEqual(refused.code, "last_admin")  # type: ignore[attr-defined]
        self.assertEqual(self._user(admin.user_id).status, "active")  # type: ignore[attr-defined]
        self.assertEqual(self._active("admin"), 1)
        teacher = self._teacher("teacher.one")
        disabled = self._disable(admin, teacher.user_id)  # type: ignore[attr-defined]
        self.assertIsInstance(disabled, Ok)
        self.assertEqual(self._user(teacher.user_id).status, "disabled")  # type: ignore[attr-defined]
        self.assertEqual(self._active("admin"), 1)
        demoted = self._role(admin, admin.user_id, "teacher")
        self.assertEqual(demoted.code, "last_admin")  # type: ignore[attr-defined]
        self.assertEqual(self._user(admin.user_id).role, "admin")  # type: ignore[attr-defined]
        invalid = self._role(admin, admin.user_id, "student")
        self.assertEqual(invalid.code, "validation_failed")  # type: ignore[attr-defined]

    def test_a_second_admin_can_leave_and_the_session_stays(self) -> None:
        admin = self._boot()
        teacher = self._teacher("teacher.one")
        promoted = self._role(admin, teacher.user_id, "admin")  # type: ignore[attr-defined]
        self.assertIsInstance(promoted, Ok)
        self.assertEqual(self._active("admin"), 2)
        self._plant("stay-1", admin.user_id)
        disabled = self._disable(admin, admin.user_id)
        self.assertIsInstance(disabled, Ok)
        self.assertEqual(self._user(admin.user_id).status, "disabled")  # type: ignore[attr-defined]
        self.assertEqual(self._active("admin"), 1)
        kept = self.world.run(lambda db: Ok(db.sessions.get("stay-1")))  # type: ignore[attr-defined]
        self.assertIsNone(kept.value.revoked_at)  # type: ignore[attr-defined]
        back = self._role(admin, teacher.user_id, "teacher")  # type: ignore[attr-defined]
        self.assertEqual(back.code, "last_admin")  # type: ignore[attr-defined]
        self.assertEqual(self._user(teacher.user_id).role, "admin")  # type: ignore[attr-defined]

    def test_zero_active_admins_still_refuses(self) -> None:
        admin = self._boot()
        teacher = self._teacher("teacher.one")

        def mark(db: object) -> Ok[None]:
            now = self.world.clock.now()
            db.users.set_status(admin.user_id, "disabled", now, now)  # type: ignore[attr-defined]
            return Ok(None)

        self.world.run(mark)
        refused = self._disable(admin, admin.user_id)
        self.assertEqual(refused.code, "last_admin")  # type: ignore[attr-defined]
        self.assertEqual(self._user(admin.user_id).status, "disabled")  # type: ignore[attr-defined]
        teacher_refused = self._disable(admin, teacher.user_id)  # type: ignore[attr-defined]
        self.assertEqual(teacher_refused.code, "last_admin")  # type: ignore[attr-defined]
        self.assertEqual(self._user(teacher.user_id).status, "active")  # type: ignore[attr-defined]

    def test_teacher_disable_and_password_reset_do_not_use_last_admin(self) -> None:
        admin = self._boot()
        teacher = self._teacher("teacher.one")
        missed = self.world.run(lambda db: disable_teacher(db, admin, admin.user_id, self.world.deps, "off"))
        self.assertEqual(missed.code, "not_found")  # type: ignore[attr-defined]
        self.assertEqual(self._user(admin.user_id).status, "active")  # type: ignore[attr-defined]
        before = self._active("admin")
        weak = self.world.run(
            lambda db: reset_teacher_password(db, admin, teacher.user_id, "short", self.world.deps, "weak")  # type: ignore[attr-defined]
        )
        self.assertEqual(weak.code, "weak_password")  # type: ignore[attr-defined]
        self.assertEqual(self._active("admin"), before)
        reset = self.world.run(
            lambda db: reset_teacher_password(db, admin, admin.user_id, NEXT_SECRET, self.world.deps, "reset")
        )
        self.assertEqual(reset.code, "not_found")  # type: ignore[attr-defined]
        self.assertEqual(self._user(admin.user_id).status, "active")  # type: ignore[attr-defined]
        self.assertEqual(self._active("admin"), before)

    def test_admin_read_records_filter_names_only(self) -> None:
        admin = self._boot()
        before = self.world.audit_count()
        listed = self.world.run(
            lambda db: list_audit_events(
                db,
                admin,
                self.world.deps,
                "read-audit",
                limit=500,
                offset=-3,
                action=NEEDLE,
                actor_user_id="",
                since=self.world.clock.now(),
                until=None,
            )
        )
        self.assertIsInstance(listed, Ok)
        self.assertEqual(self.world.audit_count() - before, 1)
        text = self.world.audit_text()
        self.assertNotIn(NEEDLE, text)
        details = [item for item in _objects(text) if "limit" in item]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["limit"], 200)
        self.assertEqual(details[0]["offset"], 0)
        self.assertEqual(details[0]["filters"], ["action", "since"])
        self.assertIn("admin_read_committed ok  audit", text)
        errors = self.world.run(
            lambda db: list_recent_errors(admin, _ring(), self.world.deps, "read-errors", limit=10, offset=0)
        )
        self.assertIsInstance(errors, Ok)
        self.assertEqual(errors.value[1], 0)  # type: ignore[index]
        text = self.world.audit_text()
        error_rows = [item for item in _objects(text) if item.get("limit") == 10 and "filters" not in item]
        self.assertEqual(error_rows, [{"limit": 10, "offset": 0}])
        self.assertIn("admin_read_committed ok  errors", text)
        self.assertNotIn(NEEDLE, text)

    def test_a_teacher_read_does_not_write_the_audit_row(self) -> None:
        self._boot()
        teacher = self._teacher("teacher.one")
        actor = Actor(teacher.user_id, "teacher", teacher.username)  # type: ignore[attr-defined]
        before = self.world.audit_count()
        listed = self.world.run(
            lambda db: list_audit_events(
                db, actor, self.world.deps, "nope", limit=10, offset=0, action="", actor_user_id="", since=None, until=None
            )
        )
        errors = self.world.run(
            lambda db: list_recent_errors(actor, _ring(), self.world.deps, "nope", limit=10, offset=0)
        )
        self.assertEqual(listed.code, "permission_denied")  # type: ignore[attr-defined]
        self.assertEqual(errors.code, "permission_denied")  # type: ignore[attr-defined]
        self.assertEqual(self.world.audit_count(), before)

    def _boot(self) -> Actor:
        result = self.world.run(lambda db: bootstrap_admin(db, "admin", ADMIN_SECRET, self.world.deps, "boot"))
        self.assertIsInstance(result, Ok)
        user = result.value
        self.assertIsNotNone(user)
        return Actor(user.user_id, user.role, user.username)  # type: ignore[union-attr]

    def _teacher(self, username: str) -> object:
        admin = Actor(self._user_id("admin"), "admin", "admin")
        result = self.world.run(lambda db: create_teacher(db, admin, username, TEACH_SECRET, self.world.deps, "teacher"))
        self.assertIsInstance(result, Ok)
        return result.value

    def _user_id(self, username: str) -> str:
        found = self.world.run(lambda db: Ok(db.users.by_username(username)))  # type: ignore[attr-defined]
        return str(found.value.user_id)  # type: ignore[attr-defined]

    def _user(self, user_id: str) -> object:
        found = self.world.run(lambda db: Ok(db.users.by_id(user_id)))  # type: ignore[attr-defined]
        return found.value

    def _active(self, role: str) -> int:
        found = self.world.run(lambda db: Ok(db.users.count_active(role)))  # type: ignore[attr-defined]
        return int(found.value)

    def _disable(self, actor: Actor, user_id: str) -> Ok[object] | Err:
        return self.world.run(lambda db: disable_user(db, actor, user_id, self.world.deps, "off"))

    def _role(self, actor: Actor, user_id: str, role: str) -> Ok[object] | Err:
        return self.world.run(lambda db: change_role(db, actor, user_id, role, self.world.deps, "role"))

    def _login(self, username: str, secret: str) -> object:
        command = LoginCommand(username, secret, digest(username), digest("203.0.113.10"))
        result = self.world.run(lambda db: login(db, command, self.world.deps, "login"))
        self.assertIsInstance(result, Ok)
        return result.value

    def _plant(self, session_id: str, user_id: str) -> None:
        now = self.world.clock.now()
        row = Session(
            session_id=session_id,
            user_id=user_id,
            csrf_token="csrf-test",
            issued_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=2),
        )

        def work(db: object) -> Ok[None]:
            db.sessions.put(row)  # type: ignore[attr-defined]
            return Ok(None)

        self.world.run(work)


class MemoryAccountTest(AccountCases, unittest.TestCase):
    def setUp(self) -> None:
        self.world = memory_world()


class PgAccountTest(AccountCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN"):
            self.skipTest("K12_PG_DSN is not set")
        self.world = pg_world()


def _objects(text: str) -> list[dict[str, object]]:
    return [json.loads(blob) for blob in re.findall(r"\{[^{}]*\}", text)]


def _ring() -> object:
    from backend.bootstrap.error_ring import ErrorRing

    return ErrorRing()
