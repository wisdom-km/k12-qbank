"""Synthetic teacher, students, and grants. Idempotent. The secret is not logged."""

from __future__ import annotations

import uuid

from backend.identity.application.deps import Deps
from backend.identity.domain.records import Grant, Student, User
from backend.kernel.result import Ok

_HASHES: dict[str, str] = {}


def seed_synthetic(
    db: object,
    deps: Deps,
    *,
    user_id: str,
    username: str,
    secret: str,
    student_ids: tuple[str, ...],
    subject_id: str,
) -> Ok[None]:
    now = deps.clock.now()
    if db.users.by_username(username) is None:  # type: ignore[attr-defined]
        db.users.insert(  # type: ignore[attr-defined]
            User(
                user_id=user_id,
                username=username,
                role="teacher",
                status="active",
                password_hash=_hash(deps, secret),
                password_algo="argon2id",
                created_at=now,
                updated_at=now,
            )
        )
    teacher = db.users.by_username(username)  # type: ignore[attr-defined]
    for student_id in student_ids:
        _student(db, student_id, subject_id, teacher.user_id, now)
        _grant(db, teacher.user_id, student_id, subject_id, now)
    return Ok(None)


def session_students(db: object, teacher_id: str) -> tuple[str, ...]:
    found: list[str] = []
    for grant in db.grants.list_all():  # type: ignore[attr-defined]
        if grant.teacher_id != teacher_id or grant.revoked_at is not None:
            continue
        if grant.student_id not in found:
            found.append(grant.student_id)
    return tuple(found)


def _student(db: object, student_id: str, subject_id: str, created_by: str, now: object) -> None:
    if db.students.by_id(student_id) is not None:  # type: ignore[attr-defined]
        return
    db.students.insert(  # type: ignore[attr-defined]
        Student(
            student_id=student_id,
            name=student_id,
            grade="g7",
            subject_id=subject_id,
            status="active",
            created_by=created_by,
            created_at=now,  # type: ignore[arg-type]
            updated_at=now,  # type: ignore[arg-type]
        )
    )


def _grant(db: object, teacher_id: str, student_id: str, subject_id: str, now: object) -> None:
    if db.grants.active(teacher_id, student_id, subject_id) is not None:  # type: ignore[attr-defined]
        return
    db.grants.insert(  # type: ignore[attr-defined]
        Grant(
            grant_id=str(uuid.uuid4()),
            teacher_id=teacher_id,
            student_id=student_id,
            subject_id=subject_id,
            granted_by=teacher_id,
            granted_at=now,  # type: ignore[arg-type]
        )
    )


def _hash(deps: Deps, secret: str) -> str:
    cached = _HASHES.get(secret)
    if cached is None:
        cached = deps.hasher.hash(secret)
        _HASHES[secret] = cached
    return cached
