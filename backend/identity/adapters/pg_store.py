"""PostgreSQL stores. SQL stays in this file. Connections come from the caller."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.errors import UniqueViolation

from backend.identity.application.conflict import Conflict
from backend.identity.domain.records import AuditRecord, Grant, Session, Student, User

_USER = """
user_id, username, role, status, password_hash, password_algo, created_at, updated_at, disabled_at
"""
_STUDENT = """
student_id, name, grade, subject_id, status, created_by, created_at, updated_at
"""
_GRANT = """
grant_id, teacher_id, student_id, subject_id, granted_by, granted_at, revoked_at
"""
_SESSION = """
session_id, user_id, csrf_token, issued_at, last_seen_at, expires_at, revoked_at, user_agent_hash, ip_hash
"""


class PgUsers:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def by_id(self, user_id: str) -> User | None:
        return _one(self._conn, f"SELECT {_USER} FROM users WHERE user_id = %s", (user_id,), _user)

    def by_username(self, username: str) -> User | None:
        return _one(self._conn, f"SELECT {_USER} FROM users WHERE username = %s", (username,), _user)

    def count_role(self, role: str) -> int:
        return _count(self._conn, "SELECT count(*) FROM users WHERE role = %s", (role,))

    def insert(self, user: User) -> None:
        _write(
            self._conn,
            f"INSERT INTO users ({_USER}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                user.user_id,
                user.username,
                user.role,
                user.status,
                user.password_hash,
                user.password_algo,
                user.created_at,
                user.updated_at,
                user.disabled_at,
            ),
        )

    def update_password(self, user_id: str, password_hash: str, algo: str, at: datetime) -> None:
        self._conn.execute(
            """
            UPDATE users
            SET password_hash = %s, password_algo = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (password_hash, algo, at, user_id),
        )

    def set_status(self, user_id: str, status: str, at: datetime, disabled_at: datetime | None) -> None:
        self._conn.execute(
            """
            UPDATE users SET status = %s, updated_at = %s, disabled_at = %s WHERE user_id = %s
            """,
            (status, at, disabled_at, user_id),
        )

    def list_role(self, role: str) -> tuple[User, ...]:
        return _many(self._conn, f"SELECT {_USER} FROM users WHERE role = %s ORDER BY username", (role,), _user)


class PgStudents:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def by_id(self, student_id: str) -> Student | None:
        return _one(self._conn, f"SELECT {_STUDENT} FROM students WHERE student_id = %s", (student_id,), _student)

    def insert(self, student: Student) -> None:
        self._conn.execute(
            f"INSERT INTO students ({_STUDENT}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                student.student_id,
                student.name,
                student.grade,
                student.subject_id,
                student.status,
                student.created_by,
                student.created_at,
                student.updated_at,
            ),
        )

    def set_status(self, student_id: str, status: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE students SET status = %s, updated_at = %s WHERE student_id = %s",
            (status, at, student_id),
        )

    def list_all(self) -> tuple[Student, ...]:
        return _many(self._conn, f"SELECT {_STUDENT} FROM students ORDER BY created_at", (), _student)


class PgGrants:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def active(self, teacher_id: str, student_id: str, subject_id: str) -> Grant | None:
        return _one(
            self._conn,
            f"""
            SELECT {_GRANT} FROM teacher_grants
            WHERE teacher_id = %s AND student_id = %s AND subject_id = %s AND revoked_at IS NULL
            """,
            (teacher_id, student_id, subject_id),
            _grant,
        )

    def by_id(self, grant_id: str) -> Grant | None:
        return _one(self._conn, f"SELECT {_GRANT} FROM teacher_grants WHERE grant_id = %s", (grant_id,), _grant)

    def insert(self, grant: Grant) -> None:
        _write(
            self._conn,
            f"INSERT INTO teacher_grants ({_GRANT}) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                grant.grant_id,
                grant.teacher_id,
                grant.student_id,
                grant.subject_id,
                grant.granted_by,
                grant.granted_at,
                grant.revoked_at,
            ),
        )

    def revoke(self, grant_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE teacher_grants SET revoked_at = %s WHERE grant_id = %s AND revoked_at IS NULL",
            (at, grant_id),
        )

    def revoke_student(self, student_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE teacher_grants SET revoked_at = %s WHERE student_id = %s AND revoked_at IS NULL",
            (at, student_id),
        )

    def list_all(self) -> tuple[Grant, ...]:
        return _many(self._conn, f"SELECT {_GRANT} FROM teacher_grants ORDER BY granted_at", (), _grant)


class PgSessions:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def put(self, session: Session) -> None:
        self._conn.execute(
            f"INSERT INTO sessions ({_SESSION}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                session.session_id,
                session.user_id,
                session.csrf_token,
                session.issued_at,
                session.last_seen_at,
                session.expires_at,
                session.revoked_at,
                session.user_agent_hash,
                session.ip_hash,
            ),
        )

    def get(self, session_id: str) -> Session | None:
        return _one(self._conn, f"SELECT {_SESSION} FROM sessions WHERE session_id = %s", (session_id,), _session)

    def revoke(self, session_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE sessions SET revoked_at = %s WHERE session_id = %s AND revoked_at IS NULL",
            (at, session_id),
        )

    def revoke_user(self, user_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE sessions SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL",
            (at, user_id),
        )

    def revoke_unexpired(self, user_id: str, at: datetime) -> int:
        cursor = self._conn.execute(
            """
            UPDATE sessions
            SET revoked_at = %s
            WHERE user_id = %s AND revoked_at IS NULL AND expires_at > %s
            """,
            (at, user_id, at),
        )
        return int(cursor.rowcount)

    def touch(self, session_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE sessions SET last_seen_at = %s WHERE session_id = %s",
            (at, session_id),
        )


class PgAttempts:
    """Each call commits on its own connection so a refused login still counts."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def add(self, username_hash: str, ip_hash: str, at: datetime, outcome: str, reason_code: str) -> None:
        _pooled(
            self._pool,
            """
            INSERT INTO login_attempts (username_hash, ip_hash, attempted_at, outcome, reason_code)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username_hash, ip_hash, at, outcome, reason_code or None),
        )

    def count_fails(self, username_hash: str, since: datetime) -> int:
        return _pooled_count(
            self._pool,
            """
            SELECT count(*) FROM login_attempts
            WHERE username_hash = %s AND outcome = 'fail' AND attempted_at >= %s
            """,
            (username_hash, since),
        )

    def count_ip(self, ip_hash: str, since: datetime) -> int:
        return _pooled_count(
            self._pool,
            "SELECT count(*) FROM login_attempts WHERE ip_hash = %s AND attempted_at >= %s",
            (ip_hash, since),
        )


class PgAudits:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def add(self, row: AuditRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_events (
                occurred_at, request_id, actor_user_id, actor_role, action,
                target_kind, target_id, reason_code, outcome, detail_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
            """,
            (
                row.occurred_at,
                row.request_id,
                row.actor_user_id or None,
                row.actor_role or None,
                row.action,
                row.target_kind or None,
                row.target_id or None,
                row.reason_code or None,
                row.outcome,
            ),
        )

    def list_rows(
        self,
        *,
        limit: int,
        offset: int,
        action: str,
        actor_user_id: str,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[tuple[AuditRecord, ...], int]:
        clauses = ["TRUE"]
        params: list[object] = []
        if action:
            clauses.append("action = %s")
            params.append(action)
        if actor_user_id:
            clauses.append("actor_user_id = %s")
            params.append(actor_user_id)
        if since is not None:
            clauses.append("occurred_at >= %s")
            params.append(since)
        if until is not None:
            clauses.append("occurred_at <= %s")
            params.append(until)
        where = " AND ".join(clauses)
        bound = tuple(params)
        total = _count(self._conn, f"SELECT count(*) FROM audit_events WHERE {where}", bound)
        rows = _many(
            self._conn,
            f"""
            SELECT occurred_at, request_id,
                   COALESCE(actor_user_id, ''), COALESCE(actor_role, ''), action,
                   COALESCE(target_kind, ''), COALESCE(target_id, ''),
                   COALESCE(reason_code, ''), outcome
            FROM audit_events
            WHERE {where}
            ORDER BY occurred_at DESC, event_id DESC
            LIMIT %s OFFSET %s
            """,
            (*bound, limit, offset),
            _audit,
        )
        return rows, total


class PgDb:
    def __init__(self, conn: Any, pool: Any) -> None:
        self.users = PgUsers(conn)
        self.students = PgStudents(conn)
        self.grants = PgGrants(conn)
        self.sessions = PgSessions(conn)
        self.attempts = PgAttempts(pool)
        self.audits = PgAudits(conn)


def _write(conn: Any, statement: str, params: tuple[object, ...]) -> None:
    try:
        conn.execute(statement, params)
    except UniqueViolation as exc:
        name = exc.diag.constraint_name or ""
        if "username" in name:
            raise Conflict("username_taken") from exc
        if name == "teacher_grants_one_active":
            raise Conflict("already_granted") from exc
        raise


def _one(conn: Any, statement: str, params: tuple[object, ...], build: Any) -> Any:
    row = conn.execute(statement, params).fetchone()
    if row is None:
        return None
    return build(row)


def _many(conn: Any, statement: str, params: tuple[object, ...], build: Any) -> tuple[Any, ...]:
    return tuple(build(row) for row in conn.execute(statement, params).fetchall())


def _count(conn: Any, statement: str, params: tuple[object, ...]) -> int:
    row = conn.execute(statement, params).fetchone()
    return int(row[0])


def _pooled(pool: Any, statement: str, params: tuple[object, ...]) -> None:
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute(statement, params)


def _pooled_count(pool: Any, statement: str, params: tuple[object, ...]) -> int:
    with pool.connection() as conn:
        with conn.transaction():
            return _count(conn, statement, params)


def _user(row: tuple[object, ...]) -> User:
    return User(
        user_id=str(row[0]),
        username=str(row[1]),
        role=str(row[2]),
        status=str(row[3]),
        password_hash=str(row[4]),
        password_algo=str(row[5]),
        created_at=row[6],  # type: ignore[arg-type]
        updated_at=row[7],  # type: ignore[arg-type]
        disabled_at=row[8],  # type: ignore[arg-type]
    )


def _student(row: tuple[object, ...]) -> Student:
    return Student(
        student_id=str(row[0]),
        name=str(row[1]),
        grade=str(row[2]),
        subject_id=str(row[3]),
        status=str(row[4]),
        created_by=str(row[5]),
        created_at=row[6],  # type: ignore[arg-type]
        updated_at=row[7],  # type: ignore[arg-type]
    )


def _grant(row: tuple[object, ...]) -> Grant:
    return Grant(
        grant_id=str(row[0]),
        teacher_id=str(row[1]),
        student_id=str(row[2]),
        subject_id=str(row[3]),
        granted_by=str(row[4]),
        granted_at=row[5],  # type: ignore[arg-type]
        revoked_at=row[6],  # type: ignore[arg-type]
    )


def _session(row: tuple[object, ...]) -> Session:
    return Session(
        session_id=str(row[0]),
        user_id=str(row[1]),
        csrf_token=str(row[2]),
        issued_at=row[3],  # type: ignore[arg-type]
        last_seen_at=row[4],  # type: ignore[arg-type]
        expires_at=row[5],  # type: ignore[arg-type]
        revoked_at=row[6],  # type: ignore[arg-type]
        user_agent_hash=str(row[7]),
        ip_hash=str(row[8]),
    )


def _audit(row: tuple[object, ...]) -> AuditRecord:
    return AuditRecord(
        occurred_at=row[0],  # type: ignore[arg-type]
        request_id=str(row[1]),
        actor_user_id=str(row[2]),
        actor_role=str(row[3]),
        action=str(row[4]),
        target_kind=str(row[5]),
        target_id=str(row[6]),
        reason_code=str(row[7]),
        outcome=str(row[8]),
    )
