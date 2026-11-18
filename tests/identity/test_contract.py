"""The same identity cases run on memory and, when configured, PostgreSQL."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from backend.identity.adapters.authorizer import GrantAuthorizer
from backend.identity.api import Actor, LoginCommand
from backend.identity.application.bootstrap_admin import bootstrap_admin
from backend.identity.application.grants import grant_teacher, list_grants, revoke_grant
from backend.identity.application.login import load_session, login, logout
from backend.identity.application.passwords import change_own_password, reset_teacher_password
from backend.identity.application.queries import list_audit_events, list_recent_errors
from backend.identity.application.students import archive_student, create_student, list_students
from backend.identity.application.teachers import create_teacher, disable_teacher, enable_teacher, list_teachers
from backend.identity.domain.digest import digest
from backend.identity.domain.records import Grant, Session
from backend.kernel.result import Err, Ok
_WORLD_PATH = Path(__file__).with_name("world.py")
_SPEC = importlib.util.spec_from_file_location("k12_identity_world", _WORLD_PATH)
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


class IdentityCases:
    world: World

    def boot(self) -> Actor:
        result = self.world.run(lambda db: bootstrap_admin(db, "admin", ADMIN_SECRET, self.world.deps, "boot"))
        self.assertIsInstance(result, Ok)
        user = result.value
        self.assertIsNotNone(user)
        return Actor(user.user_id, user.role, user.username)  # type: ignore[union-attr]

    def test_bootstrap_runs_once(self) -> None:
        admin = self.boot()
        before = self.world.audit_count()
        again = self.world.run(lambda db: bootstrap_admin(db, "admin", ADMIN_SECRET, self.world.deps, "boot2"))
        self.assertIsInstance(again, Ok)
        self.assertIsNone(again.value)
        self.assertEqual(self.world.audit_count(), before)
        self.assertEqual(admin.role, "admin")

    def test_create_teacher_rejects_a_duplicate_name(self) -> None:
        admin = self.boot()
        first = self._teacher(admin, "teacher.one")
        before = self.world.audit_count()
        second = self._teacher(admin, "teacher.one")
        self.assertEqual(second.code, "username_taken")  # type: ignore[attr-defined]
        self.assertEqual(self.world.audit_count() - before, 1)
        self.assertIn("username_taken", self.world.audit_text())
        self.assertEqual(first.value.username, "teacher.one")  # type: ignore[attr-defined]

    def test_disabled_teacher_cannot_sign_in(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        signed = self._login("teacher.one", TEACH_SECRET)
        self.world.run(lambda db: disable_teacher(db, admin, teacher.user_id, self.world.deps, "off"))  # type: ignore[attr-defined]
        refused = self._login("teacher.one", TEACH_SECRET)
        self.assertEqual(refused.code, "invalid_credentials")
        loaded = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNone(loaded.value)

    def test_teacher_cannot_run_admin_commands(self) -> None:
        teacher = Actor("teacher-1", "teacher", "teacher.one")
        calls = (
            lambda db: create_teacher(db, teacher, "other.one", TEACH_SECRET, self.world.deps, "r"),
            lambda db: disable_teacher(db, teacher, "teacher-1", self.world.deps, "r"),
            lambda db: create_student(db, teacher, "Sample", "g7", "math", self.world.deps, "r"),
            lambda db: archive_student(db, teacher, "student-1", self.world.deps, "r"),
            lambda db: grant_teacher(db, teacher, "teacher-1", "student-1", "math", self.world.deps, "r"),
            lambda db: revoke_grant(db, teacher, "teacher-1", "student-1", "math", self.world.deps, "r"),
            lambda db: reset_teacher_password(db, teacher, "teacher-1", NEXT_SECRET, self.world.deps, "r"),
            lambda db: list_teachers(db, teacher, self.world.deps, "r"),
            lambda db: list_students(db, teacher),
            lambda db: list_grants(db, teacher),
            lambda db: list_audit_events(
                db, teacher, self.world.deps, "r", limit=10, offset=0, action="", actor_user_id="", since=None, until=None
            ),
            lambda db: list_recent_errors(teacher, _ring(self), self.world.deps, "r", limit=10, offset=0),
        )
        for call in calls:
            result = self.world.run(call)
            self.assertIsInstance(result, Err)
            self.assertEqual(result.code, "permission_denied")

    def test_grant_then_revoke_flips_the_authorizer(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        student = self._student(admin, "Sample Student").value
        granted = self._grant(admin, teacher.user_id, student.student_id)  # type: ignore[attr-defined]
        self.assertTrue(self._allow(teacher.user_id, student.student_id))  # type: ignore[attr-defined]
        self.world.run(
            lambda db: revoke_grant(db, admin, teacher.user_id, student.student_id, "math", self.world.deps, "revoke")  # type: ignore[attr-defined]
        )
        self.assertFalse(self._allow(teacher.user_id, student.student_id))  # type: ignore[attr-defined]
        self.assertEqual(granted.value.subject_id, "math")  # type: ignore[attr-defined]

    def test_repeat_grant_keeps_the_same_row_and_audits(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        student = self._student(admin, "Sample Student").value
        first = self._grant(admin, teacher.user_id, student.student_id)  # type: ignore[attr-defined]
        before = self.world.audit_count()
        second = self._grant(admin, teacher.user_id, student.student_id)  # type: ignore[attr-defined]
        self.assertEqual(first.value.grant_id, second.value.grant_id)  # type: ignore[attr-defined]
        self.assertEqual(self.world.audit_count() - before, 1)

    def test_login_rotates_the_session(self) -> None:
        admin = self.boot()
        self._teacher(admin, "teacher.one")
        first = self._login("teacher.one", TEACH_SECRET)
        second = self._login("teacher.one", TEACH_SECRET)
        self.assertNotEqual(first.value.session_id, second.value.session_id)  # type: ignore[attr-defined]
        old = self.world.run(lambda db: Ok(load_session(db, first.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        current = self.world.run(lambda db: Ok(load_session(db, second.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNone(old.value)
        self.assertIsNotNone(current.value)
        self.assertTrue(any(event.event == "login_succeeded" for event in self.world.runtime.events))

    def test_idle_session_is_revoked(self) -> None:
        admin = self.boot()
        self._teacher(admin, "teacher.one")
        signed = self._login("teacher.one", TEACH_SECRET)
        self.world.clock.advance(timedelta(minutes=61))
        loaded = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNone(loaded.value)

    def test_logout_revokes_the_session(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        signed = self._login("teacher.one", TEACH_SECRET)
        actor = Actor(teacher.user_id, "teacher", teacher.username)  # type: ignore[attr-defined]
        self.world.run(lambda db: logout(db, actor, signed.value.session_id, self.world.deps, "out"))  # type: ignore[attr-defined]
        loaded = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNone(loaded.value)
        self.assertTrue(any(event.event == "session_revoked" for event in self.world.runtime.events))

    def test_fifth_failure_is_credentials_and_sixth_locks(self) -> None:
        admin = self.boot()
        self._teacher(admin, "teacher.one")
        for _ in range(5):
            failed = self._login("teacher.one", "wrong-pass1")
            self.assertEqual(failed.code, "invalid_credentials")
        locked = self._login("teacher.one", "wrong-pass1")
        self.assertEqual(locked.code, "account_locked")

    def test_password_change_and_admin_reset(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        actor = Actor(teacher.user_id, "teacher", teacher.username)  # type: ignore[attr-defined]
        changed = self.world.run(
            lambda db: change_own_password(db, actor, TEACH_SECRET, NEXT_SECRET, self.world.deps, "pw")
        )
        self.assertIsInstance(changed, Ok)
        self.assertIsInstance(self._login("teacher.one", NEXT_SECRET), Ok)
        self.world.run(lambda db: reset_teacher_password(db, admin, teacher.user_id, TEACH_SECRET, self.world.deps, "reset"))  # type: ignore[attr-defined]
        self.assertIsInstance(self._login("teacher.one", TEACH_SECRET), Ok)

    def test_revoke_skips_expired_and_already_revoked(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        now = self.world.clock.now()
        user_id = teacher.user_id  # type: ignore[attr-defined]
        self._put_session("live-1", user_id, expires_at=now + timedelta(hours=2))
        self._put_session("old-exp", user_id, expires_at=now - timedelta(minutes=1))
        earlier = now - timedelta(days=1)
        self._put_session("gone-1", user_id, expires_at=now + timedelta(hours=2), revoked_at=earlier)
        result = self.world.run(lambda db: disable_teacher(db, admin, user_id, self.world.deps, "off"))
        self.assertIsInstance(result, Ok)
        self.assertIsNotNone(self._session("live-1").revoked_at)  # type: ignore[attr-defined]
        self.assertIsNone(self._session("old-exp").revoked_at)  # type: ignore[attr-defined]
        self.assertEqual(self._session("gone-1").revoked_at, earlier)  # type: ignore[attr-defined]
        self.assertEqual(self._revoked_counts()[-1], "1")
        text = self.world.audit_text()
        self.assertIn("session_revoked", text)
        self.assertNotIn("session_revoked 1", text)
        self.assertNotIn("live-1", text)
        self.assertNotIn("old-exp", text)
        self.assertNotIn("gone-1", text)

    def test_enable_revokes_a_session_planted_while_disabled(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        user_id = teacher.user_id  # type: ignore[attr-defined]
        self.world.run(lambda db: disable_teacher(db, admin, user_id, self.world.deps, "off"))
        now = self.world.clock.now()
        self._put_session("while-off", user_id, expires_at=now + timedelta(hours=2))
        enabled = self.world.run(lambda db: enable_teacher(db, admin, user_id, self.world.deps, "on"))
        self.assertIsInstance(enabled, Ok)
        self.assertEqual(enabled.value.status, "active")  # type: ignore[attr-defined]
        self.assertIsNotNone(self._session("while-off").revoked_at)  # type: ignore[attr-defined]
        self.assertEqual(self._revoked_counts()[-1], "1")
        self._put_session("still-on", user_id, expires_at=now + timedelta(hours=3))
        again = self.world.run(lambda db: enable_teacher(db, admin, user_id, self.world.deps, "on2"))
        self.assertIsInstance(again, Err)
        self.assertEqual(again.code, "validation_failed")
        self.assertIsNone(self._session("still-on").revoked_at)  # type: ignore[attr-defined]

    def test_failed_paths_do_not_revoke(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        user_id = teacher.user_id  # type: ignore[attr-defined]
        signed = self._login("teacher.one", TEACH_SECRET)
        actor = Actor(user_id, "teacher", teacher.username)  # type: ignore[attr-defined]
        denied = self.world.run(lambda db: disable_teacher(db, actor, user_id, self.world.deps, "no"))
        self.assertEqual(denied.code, "permission_denied")
        weak = self.world.run(
            lambda db: reset_teacher_password(db, admin, user_id, "short", self.world.deps, "weak")
        )
        self.assertEqual(weak.code, "weak_password")
        missing = self.world.run(
            lambda db: reset_teacher_password(db, admin, "missing-user", NEXT_SECRET, self.world.deps, "miss")
        )
        self.assertEqual(missing.code, "not_found")
        loaded = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNotNone(loaded.value)
        self.world.run(lambda db: disable_teacher(db, admin, user_id, self.world.deps, "off"))
        now = self.world.clock.now()
        self._put_session("stay-1", user_id, expires_at=now + timedelta(hours=2))
        again = self.world.run(lambda db: disable_teacher(db, admin, user_id, self.world.deps, "off2"))
        self.assertEqual(again.code, "validation_failed")
        self.assertIsNone(self._session("stay-1").revoked_at)  # type: ignore[attr-defined]

    def test_reset_revokes_and_change_own_does_not(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        user_id = teacher.user_id  # type: ignore[attr-defined]
        actor = Actor(user_id, "teacher", teacher.username)  # type: ignore[attr-defined]
        signed = self._login("teacher.one", TEACH_SECRET)
        changed = self.world.run(
            lambda db: change_own_password(db, actor, TEACH_SECRET, NEXT_SECRET, self.world.deps, "pw")
        )
        self.assertIsInstance(changed, Ok)
        still = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNotNone(still.value)
        reset = self.world.run(
            lambda db: reset_teacher_password(db, admin, user_id, TEACH_SECRET, self.world.deps, "reset")
        )
        self.assertIsInstance(reset, Ok)
        gone = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNone(gone.value)
        self.assertEqual(self._revoked_counts()[-1], "1")
        self.assertIsInstance(self._login("teacher.one", TEACH_SECRET), Ok)

    def test_archive_removes_the_grant(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        student = self._student(admin, "Sample Student").value
        self._grant(admin, teacher.user_id, student.student_id)  # type: ignore[attr-defined]
        self.world.run(lambda db: archive_student(db, admin, student.student_id, self.world.deps, "arc"))  # type: ignore[attr-defined]
        self.assertFalse(self._allow(teacher.user_id, student.student_id))  # type: ignore[attr-defined]
        self.assertNotIn("Sample Student", self.world.audit_text())

    def test_write_success_and_failure_each_add_one_audit_row(self) -> None:
        admin = self.boot()
        before = self.world.audit_count()
        self._teacher(admin, "teacher.one")
        self.assertEqual(self.world.audit_count() - before, 1)
        self.assertIn("admin_action_committed", self.world.audit_text())
        before = self.world.audit_count()
        self._login("missing.user", TEACH_SECRET)
        self.assertEqual(self.world.audit_count() - before, 1)
        self.assertIn("err", self.world.audit_text())

    def test_second_active_grant_conflicts(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value
        student = self._student(admin, "Sample Student").value
        self._grant(admin, teacher.user_id, student.student_id)  # type: ignore[attr-defined]

        def work(db: object) -> Ok[object]:
            row = Grant(
                "grant-race",
                teacher.user_id,  # type: ignore[attr-defined]
                student.student_id,  # type: ignore[attr-defined]
                "math",
                admin.user_id,
                self.world.clock.now(),
            )
            db.grants.insert(row)  # type: ignore[attr-defined]
            return Ok(row)

        result = self.world.run(work)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.code, "already_granted")

    def test_duplicate_insert_returns_username_taken(self) -> None:
        admin = self.boot()
        saved = self._teacher(admin, "teacher.one").value

        def work(db: object) -> Ok[object]:
            twin = replace(saved, user_id="other-user")  # type: ignore[arg-type]
            db.users.insert(twin)  # type: ignore[attr-defined]
            return Ok(twin)

        result = self.world.run(work)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.code, "username_taken")
        kept = self.world.run(lambda db: Ok(db.users.by_username("teacher.one")))  # type: ignore[attr-defined]
        other = self.world.run(lambda db: Ok(db.users.by_id("other-user")))  # type: ignore[attr-defined]
        self.assertEqual(kept.value.user_id, saved.user_id)  # type: ignore[attr-defined]
        self.assertIsNone(other.value)

    def test_rehash_replaces_an_old_hash(self) -> None:
        admin = self.boot()
        teacher = self._teacher(admin, "teacher.one").value

        def mark(db: object) -> Ok[None]:
            db.users.update_password(teacher.user_id, "old:" + TEACH_SECRET, "argon2id", self.world.clock.now())  # type: ignore[attr-defined]
            return Ok(None)

        self.world.run(mark)
        signed = self._login("teacher.one", TEACH_SECRET)
        self.assertIsInstance(signed, Ok)
        stored = self.world.run(lambda db: Ok(db.users.by_id(teacher.user_id)))  # type: ignore[attr-defined]
        self.assertTrue(str(stored.value.password_hash).startswith("v1:"))  # type: ignore[attr-defined]

    def test_admin_can_read_audit_and_recent_errors(self) -> None:
        admin = self.boot()
        listed = self.world.run(
            lambda db: list_audit_events(
                db,
                admin,
                self.world.deps,
                "read",
                limit=10,
                offset=0,
                action="bootstrap_admin",
                actor_user_id="",
                since=None,
                until=None,
            )
        )
        self.assertIsInstance(listed, Ok)
        self.assertGreaterEqual(listed.value[1], 1)  # type: ignore[index]
        errors = self.world.run(
            lambda db: list_recent_errors(admin, _ring(self), self.world.deps, "errs", limit=10, offset=0)
        )
        self.assertIsInstance(errors, Ok)
        self.assertEqual(errors.value[1], 1)  # type: ignore[index]

    def test_absolute_expiry_revokes_the_session(self) -> None:
        self.world = self.fresh(timedelta(hours=48), timedelta(hours=12))
        admin = self.boot()
        self._teacher(admin, "teacher.one")
        signed = self._login("teacher.one", TEACH_SECRET)
        self.world.clock.advance(timedelta(hours=13))
        loaded = self.world.run(lambda db: Ok(load_session(db, signed.value.session_id, self.world.deps)))  # type: ignore[attr-defined]
        self.assertIsNone(loaded.value)

    def fresh(self, idle: timedelta, absolute: timedelta) -> World:
        raise NotImplementedError

    def _teacher(self, admin: Actor, username: str) -> Ok[object] | Err:
        return self.world.run(lambda db: create_teacher(db, admin, username, TEACH_SECRET, self.world.deps, "teacher"))

    def _student(self, admin: Actor, name: str) -> Ok[object] | Err:
        result = self.world.run(lambda db: create_student(db, admin, name, "g7", "math", self.world.deps, "student"))
        self.assertIsInstance(result, Ok)
        return result

    def _grant(self, admin: Actor, teacher_id: str, student_id: str) -> Ok[object] | Err:
        result = self.world.run(
            lambda db: grant_teacher(db, admin, teacher_id, student_id, "math", self.world.deps, "grant")
        )
        self.assertIsInstance(result, Ok)
        return result

    def _login(self, username: str, secret: str) -> Ok[object] | Err:
        command = LoginCommand(username, secret, digest(username), digest("203.0.113.10"))
        return self.world.run(lambda db: login(db, command, self.world.deps, "login"))

    def _allow(self, teacher_id: str, student_id: str) -> bool:
        result = self.world.run(lambda db: Ok(GrantAuthorizer(db.grants).allow(teacher_id, student_id, "math")))  # type: ignore[attr-defined]
        return bool(result.value)

    def _put_session(
        self,
        session_id: str,
        user_id: str,
        *,
        expires_at: object,
        revoked_at: object | None = None,
    ) -> None:
        now = self.world.clock.now()
        row = Session(
            session_id=session_id,
            user_id=user_id,
            csrf_token="csrf-test",
            issued_at=now,
            last_seen_at=now,
            expires_at=expires_at,  # type: ignore[arg-type]
            revoked_at=revoked_at,  # type: ignore[arg-type]
        )

        def work(db: object) -> Ok[None]:
            db.sessions.put(row)  # type: ignore[attr-defined]
            return Ok(None)

        self.world.run(work)

    def _session(self, session_id: str) -> object:
        found: dict[str, object] = {}

        def work(db: object) -> Ok[object]:
            found["row"] = db.sessions.get(session_id)  # type: ignore[attr-defined]
            return Ok(found["row"])

        self.world.run(work)
        return found["row"]

    def _revoked_counts(self) -> list[str]:
        return [event.outcome for event in self.world.runtime.events if event.event == "session_revoked"]

class MemoryContractTest(IdentityCases, unittest.TestCase):
    def setUp(self) -> None:
        self.world = memory_world()

    def fresh(self, idle: timedelta, absolute: timedelta) -> World:
        return memory_world(idle, absolute)


class PgContractTest(IdentityCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN"):
            self.skipTest("K12_PG_DSN is not set")
        self.world = pg_world()

    def fresh(self, idle: timedelta, absolute: timedelta) -> World:
        return pg_world(idle, absolute)


def _ring(case: IdentityCases) -> object:
    from backend.bootstrap.error_ring import ErrorRing
    from backend.kernel.log_event import LogEvent

    ring = ErrorRing()
    ring.add(
        LogEvent(
            time=case.world.clock.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            level="ERROR",
            event="use_case_failed",
            request_id="err-1",
            module="identity",
            outcome="store_failed",
            duration_ms=1,
        )
    )
    return ring


class DirectConflictTest(unittest.TestCase):
    def test_memory_grant_conflict_uses_the_stable_code(self) -> None:
        from backend.identity.application.conflict import Conflict
        from backend.identity.domain.records import Grant

        db_world = memory_world()
        now = db_world.clock.now()
        grant = Grant("g1", "t1", "s1", "math", "admin", now)
        db = _memory_db(db_world)
        db.grants.insert(grant)
        with self.assertRaises(Conflict) as caught:
            db.grants.insert(replace(grant, grant_id="g2"))
        self.assertEqual(caught.exception.code, "already_granted")


def _memory_db(world: World) -> object:
    holder: list[object] = []

    def work(db: object) -> Ok[object]:
        holder.append(db)
        return Ok(None)

    world.run(work)
    return holder[0]
