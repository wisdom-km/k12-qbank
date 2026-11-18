"""Session and login-attempt retention against PostgreSQL. Skips without a DSN.

Does not truncate the database. Inserts one throwaway user and deletes only those rows.
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
SESSION_BEFORE = NOW - timedelta(days=30)
ATTEMPT_BEFORE = NOW - timedelta(days=30)
AUDIT_BEFORE = NOW - timedelta(days=1825)


class SessionRetentionPgTest(unittest.TestCase):
    def test_expired_sessions_are_marked_and_old_rows_are_deleted(self) -> None:
        dsn = os.environ.get("K12_PG_DSN", "").strip()
        if not dsn:
            self.skipTest("K12_PG_DSN is not set")
        user_id = "c3ret-" + uuid.uuid4().hex
        attempt_hash = "c3att-" + uuid.uuid4().hex
        old_audit = "c3-audit-old-" + uuid.uuid4().hex
        new_audit = "c3-audit-new-" + uuid.uuid4().hex
        try:
            _insert_user(dsn, user_id, NOW)
            _insert_session(dsn, "c3-expired", user_id, NOW - timedelta(hours=1), None, NOW)
            _insert_session(dsn, "c3-old-revoked", user_id, NOW + timedelta(hours=1), NOW - timedelta(days=40), NOW)
            _insert_session(dsn, "c3-recent-revoked", user_id, NOW + timedelta(hours=1), NOW - timedelta(days=1), NOW)
            _insert_session(dsn, "c3-boundary-revoked", user_id, NOW + timedelta(hours=1), SESSION_BEFORE, NOW)
            _insert_session(dsn, "c3-live", user_id, NOW + timedelta(hours=2), None, NOW)
            _insert_attempt(dsn, attempt_hash, NOW - timedelta(days=31))
            _insert_attempt(dsn, attempt_hash, ATTEMPT_BEFORE)
            _insert_attempt(dsn, attempt_hash, NOW - timedelta(days=1))
            _insert_audit(dsn, old_audit, NOW - timedelta(days=2000))
            _insert_audit(dsn, new_audit, NOW - timedelta(days=1))
            from backend.identity.adapters.pg_retention import retain_rows

            marked, deleted_sessions, deleted_attempts = retain_rows(
                dsn,
                now=NOW,
                audit_before=AUDIT_BEFORE,
                session_before=SESSION_BEFORE,
                attempt_before=ATTEMPT_BEFORE,
            )
            self.assertGreaterEqual(marked, 1)
            self.assertGreaterEqual(deleted_sessions, 1)
            self.assertGreaterEqual(deleted_attempts, 1)
            rows = {row[0]: row[1] for row in _sessions(dsn, user_id)}
            self.assertEqual(set(rows), {"c3-expired", "c3-recent-revoked", "c3-boundary-revoked", "c3-live"})
            self.assertIsNotNone(rows["c3-expired"])
            self.assertIsNone(rows["c3-live"])
            self.assertEqual(_attempt_count(dsn, attempt_hash, older_than=ATTEMPT_BEFORE), 0)
            self.assertEqual(_attempt_count(dsn, attempt_hash, older_than=None), 2)
            self.assertEqual(_audit_count(dsn, old_audit), 0)
            self.assertEqual(_audit_count(dsn, new_audit), 1)
        finally:
            _cleanup(dsn, user_id, attempt_hash, old_audit, new_audit)


def _connect(dsn: str) -> object:
    import psycopg

    return psycopg.connect(dsn, autocommit=True)


def _insert_user(dsn: str, user_id: str, now: datetime) -> None:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        conn.execute(
            """
            INSERT INTO users (
                user_id, username, role, status, password_hash, password_algo, created_at, updated_at
            ) VALUES (%s, %s, 'teacher', 'active', 'not-a-secret', 'argon2id', %s, %s)
            """,
            (user_id, user_id, now, now),
        )


def _insert_session(
    dsn: str,
    session_id: str,
    user_id: str,
    expires_at: datetime,
    revoked_at: datetime | None,
    now: datetime,
) -> None:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, csrf_token, issued_at, last_seen_at, expires_at, revoked_at
            ) VALUES (%s, %s, 'csrf-test', %s, %s, %s, %s)
            """,
            (session_id, user_id, now, now, expires_at, revoked_at),
        )


def _insert_attempt(dsn: str, username_hash: str, attempted_at: datetime) -> None:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        conn.execute(
            """
            INSERT INTO login_attempts (username_hash, ip_hash, attempted_at, outcome)
            VALUES (%s, 'c3-ip', %s, 'fail')
            """,
            (username_hash, attempted_at),
        )


def _insert_audit(dsn: str, request_id: str, occurred_at: datetime) -> None:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        conn.execute(
            """
            INSERT INTO audit_events (occurred_at, request_id, action, outcome)
            VALUES (%s, %s, 'c3_probe', 'ok')
            """,
            (occurred_at, request_id),
        )


def _sessions(dsn: str, user_id: str) -> list[tuple[str, object]]:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        return list(
            conn.execute(
                "SELECT session_id, revoked_at FROM sessions WHERE user_id = %s",
                (user_id,),
            ).fetchall()
        )


def _attempt_count(dsn: str, username_hash: str, *, older_than: datetime | None) -> int:
    if older_than is None:
        statement = "SELECT count(*) FROM login_attempts WHERE username_hash = %s"
        params: tuple[object, ...] = (username_hash,)
    else:
        statement = "SELECT count(*) FROM login_attempts WHERE username_hash = %s AND attempted_at < %s"
        params = (username_hash, older_than)
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        return int(conn.execute(statement, params).fetchone()[0])


def _audit_count(dsn: str, request_id: str) -> int:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT count(*) FROM audit_events WHERE request_id = %s",
            (request_id,),
        ).fetchone()
    return int(row[0])


def _cleanup(dsn: str, user_id: str, username_hash: str, old_audit: str, new_audit: str) -> None:
    with _connect(dsn) as conn:  # type: ignore[attr-defined]
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM login_attempts WHERE username_hash = %s", (username_hash,))
        conn.execute("DELETE FROM audit_events WHERE request_id = %s", (old_audit,))
        conn.execute("DELETE FROM audit_events WHERE request_id = %s", (new_audit,))
        conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
