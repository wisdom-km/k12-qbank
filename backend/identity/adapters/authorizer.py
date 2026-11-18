"""Practice calls allow(). This adapter does not import practice."""

from __future__ import annotations

from backend.identity.application.ports import GrantStore


class GrantAuthorizer:
    def __init__(self, grants: GrantStore) -> None:
        self._grants = grants

    def allow(self, teacher_id: str, student_id: str, subject_id: str) -> bool:
        return self._grants.active(teacher_id, student_id, subject_id) is not None


class PoolGrantReader:
    """Read grants through the pool. practice still only calls allow()."""

    def __init__(self, pool: object) -> None:
        self._pool = pool

    def active(self, teacher_id: str, student_id: str, subject_id: str):  # type: ignore[no-untyped-def]
        from backend.identity.adapters.pg_store import PgGrants

        with self._pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                return PgGrants(conn).active(teacher_id, student_id, subject_id)
