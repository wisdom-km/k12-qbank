"""Retention SQL for sessions, login attempts, and audit rows."""

from __future__ import annotations

from datetime import datetime


def retain_rows(
    dsn: str,
    *,
    now: datetime,
    audit_before: datetime,
    session_before: datetime,
    attempt_before: datetime,
) -> tuple[int, int, int]:
    """Mark expired sessions, then delete old revoked rows and old attempts.

    A row marked in this call keeps revoked_at = now, so the delete predicate
    does not remove it in the same transaction.
    """
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.transaction():
            marked = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = %s
                WHERE expires_at <= %s AND revoked_at IS NULL
                """,
                (now, now),
            ).rowcount
            deleted_sessions = conn.execute(
                """
                DELETE FROM sessions
                WHERE revoked_at IS NOT NULL AND revoked_at < %s
                """,
                (session_before,),
            ).rowcount
            deleted_attempts = conn.execute(
                "DELETE FROM login_attempts WHERE attempted_at < %s",
                (attempt_before,),
            ).rowcount
            conn.execute(
                "DELETE FROM audit_events WHERE occurred_at < %s",
                (audit_before,),
            )
    return int(marked), int(deleted_sessions), int(deleted_attempts)
