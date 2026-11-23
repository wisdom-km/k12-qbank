"""In-memory stores for tests and the synthetic process."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from backend.identity.application.conflict import Conflict
from backend.identity.domain.records import AuditRecord, Grant, Session, Student, User
from backend.kernel.log_event import LogEvent


class MemoryUsers:
    def __init__(self) -> None:
        self._rows: dict[str, User] = {}

    def by_id(self, user_id: str) -> User | None:
        return self._rows.get(user_id)

    def by_username(self, username: str) -> User | None:
        for user in self._rows.values():
            if user.username == username:
                return user
        return None

    def count_role(self, role: str) -> int:
        return sum(1 for user in self._rows.values() if user.role == role)

    def insert(self, user: User) -> None:
        if self.by_username(user.username) is not None:
            raise Conflict("username_taken")
        self._rows[user.user_id] = user

    def update_password(self, user_id: str, password_hash: str, algo: str, at: datetime) -> None:
        current = self._rows[user_id]
        self._rows[user_id] = replace(current, password_hash=password_hash, password_algo=algo, updated_at=at)

    def set_status(self, user_id: str, status: str, at: datetime, disabled_at: datetime | None) -> None:
        current = self._rows[user_id]
        self._rows[user_id] = replace(current, status=status, updated_at=at, disabled_at=disabled_at)

    def count_active(self, role: str) -> int:
        return sum(1 for user in self._rows.values() if user.role == role and user.status == "active")

    def set_role(self, user_id: str, role: str, at: datetime) -> None:
        current = self._rows[user_id]
        self._rows[user_id] = replace(current, role=role, updated_at=at)

    def set_must_change(self, user_id: str, value: bool, at: datetime) -> None:
        current = self._rows[user_id]
        self._rows[user_id] = replace(current, must_change_password=value, updated_at=at)

    def list_role(self, role: str) -> tuple[User, ...]:
        return tuple(user for user in self._rows.values() if user.role == role)


class MemoryStudents:
    def __init__(self) -> None:
        self._rows: dict[str, Student] = {}

    def by_id(self, student_id: str) -> Student | None:
        return self._rows.get(student_id)

    def by_external_id(self, external_id: str) -> Student | None:
        for student in self._rows.values():
            if student.external_id == external_id:
                return student
        return None

    def insert(self, student: Student) -> None:
        taken = self.by_external_id(student.external_id)
        if taken is not None:
            raise Conflict("external_id_taken")
        self._rows[student.student_id] = student

    def update(self, student: Student) -> None:
        taken = self.by_external_id(student.external_id)
        if taken is not None and taken.student_id != student.student_id:
            raise Conflict("external_id_taken")
        self._rows[student.student_id] = student

    def set_status(self, student_id: str, status: str, at: datetime) -> None:
        current = self._rows[student_id]
        self._rows[student_id] = replace(current, status=status, updated_at=at)

    def list_all(self) -> tuple[Student, ...]:
        return tuple(self._rows.values())


class MemoryGrants:
    def __init__(self) -> None:
        self._rows: dict[str, Grant] = {}

    def active(self, teacher_id: str, student_id: str, subject_id: str) -> Grant | None:
        for grant in self._rows.values():
            if _same_grant(grant, teacher_id, student_id, subject_id) and grant.revoked_at is None:
                return grant
        return None

    def by_id(self, grant_id: str) -> Grant | None:
        return self._rows.get(grant_id)

    def insert(self, grant: Grant) -> None:
        if self.active(grant.teacher_id, grant.student_id, grant.subject_id) is not None:
            raise Conflict("already_granted")
        self._rows[grant.grant_id] = grant

    def revoke(self, grant_id: str, at: datetime) -> None:
        current = self._rows[grant_id]
        self._rows[grant_id] = replace(current, revoked_at=at)

    def revoke_student(self, student_id: str, at: datetime) -> None:
        for grant_id, grant in list(self._rows.items()):
            if grant.student_id == student_id and grant.revoked_at is None:
                self._rows[grant_id] = replace(grant, revoked_at=at)

    def list_all(self) -> tuple[Grant, ...]:
        return tuple(self._rows.values())


class MemorySessions:
    def __init__(self) -> None:
        self._rows: dict[str, Session] = {}

    def put(self, session: Session) -> None:
        self._rows[session.session_id] = session

    def get(self, session_id: str) -> Session | None:
        return self._rows.get(session_id)

    def revoke(self, session_id: str, at: datetime) -> None:
        current = self._rows.get(session_id)
        if current is not None and current.revoked_at is None:
            self._rows[session_id] = replace(current, revoked_at=at)

    def revoke_user(self, user_id: str, at: datetime) -> None:
        for session_id, session in list(self._rows.items()):
            if session.user_id == user_id and session.revoked_at is None:
                self._rows[session_id] = replace(session, revoked_at=at)

    def revoke_unexpired(self, user_id: str, at: datetime) -> int:
        count = 0
        for session_id, session in list(self._rows.items()):
            if session.user_id != user_id or session.revoked_at is not None:
                continue
            if session.expires_at <= at:
                continue
            self._rows[session_id] = replace(session, revoked_at=at)
            count += 1
        return count

    def list_unexpired(self, user_id: str, at: datetime) -> tuple[Session, ...]:
        chosen = [
            session
            for session in self._rows.values()
            if session.user_id == user_id and session.revoked_at is None and session.expires_at > at
        ]
        chosen.sort(key=lambda session: session.last_seen_at, reverse=True)
        return tuple(chosen)

    def touch(self, session_id: str, at: datetime) -> None:
        current = self._rows[session_id]
        self._rows[session_id] = replace(current, last_seen_at=at)


class MemoryAttempts:
    def __init__(self) -> None:
        self._rows: list[tuple[str, str, datetime, str, str]] = []

    def add(self, username_hash: str, ip_hash: str, at: datetime, outcome: str, reason_code: str) -> None:
        self._rows.append((username_hash, ip_hash, at, outcome, reason_code))

    def count_fails(self, username_hash: str, since: datetime) -> int:
        return sum(1 for row in self._rows if row[0] == username_hash and row[3] == "fail" and row[2] >= since)

    def count_ip(self, ip_hash: str, since: datetime) -> int:
        return sum(1 for row in self._rows if row[1] == ip_hash and row[2] >= since)


class MemoryAuditBook:
    """Audit sink and reader. Rows stay in the process."""

    def __init__(self) -> None:
        self.rows: list[AuditRecord] = []
        self.events: list[LogEvent] = []

    def write_audit(self, event: LogEvent) -> None:
        self.events.append(event)
        self.add(_record(event))

    def add(self, row: AuditRecord) -> None:
        self.rows.append(row)

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
        chosen = [row for row in self.rows if _keep(row, action, actor_user_id, since, until)]
        chosen.sort(key=lambda row: row.occurred_at, reverse=True)
        return tuple(chosen[offset : offset + limit]), len(chosen)


class MemoryDb:
    def __init__(self) -> None:
        self.users = MemoryUsers()
        self.students = MemoryStudents()
        self.grants = MemoryGrants()
        self.sessions = MemorySessions()
        self.attempts = MemoryAttempts()
        self.audits = MemoryAuditBook()


def _same_grant(grant: Grant, teacher_id: str, student_id: str, subject_id: str) -> bool:
    return grant.teacher_id == teacher_id and grant.student_id == student_id and grant.subject_id == subject_id


def _record(event: LogEvent) -> AuditRecord:
    parsed = datetime.strptime(event.time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return AuditRecord(
        occurred_at=parsed,
        request_id=event.request_id,
        actor_user_id=event.actor_user_id,
        actor_role=event.actor_role,
        action=event.action or event.event,
        target_kind=event.target_kind,
        target_id=event.target_id,
        reason_code=event.reason_code,
        outcome=event.outcome if event.outcome in {"ok", "err"} else "err",
        detail_json=event.detail,
    )


def _keep(row: AuditRecord, action: str, actor_user_id: str, since: datetime | None, until: datetime | None) -> bool:
    if action and row.action != action:
        return False
    if actor_user_id and row.actor_user_id != actor_user_id:
        return False
    if since is not None and row.occurred_at < since:
        return False
    if until is not None and row.occurred_at > until:
        return False
    return True
