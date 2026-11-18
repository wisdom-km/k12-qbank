"""Admin creates and archives students. Names stay out of the audit row."""

from __future__ import annotations

import uuid

from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.application.notes import note, started
from backend.identity.domain.records import Student
from backend.identity.domain.rules import can_archive, label_ok, subject_ok
from backend.kernel.result import Err, Ok


def create_student(db: object, actor: object, name: str, grade: str, subject_id: str, deps: Deps, request_id: str) -> Ok[Student] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id="", outcome="err", reason_code="permission_denied")
        return refused
    if not label_ok(name, 80) or not label_ok(grade, 32) or not subject_ok(subject_id):
        note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id="", outcome="err", reason_code="validation_failed")
        return Err("validation_failed", "validation_failed")
    now = deps.clock.now()
    student = Student(
        student_id=str(uuid.uuid4()),
        name=name.strip(),
        grade=grade.strip(),
        subject_id=subject_id,
        status="active",
        created_by=getattr(actor, "user_id", ""),
        created_at=now,
        updated_at=now,
    )
    db.students.insert(student)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id=student.student_id, outcome="ok")
    return Ok(student)


def archive_student(db: object, actor: object, student_id: str, deps: Deps, request_id: str) -> Ok[Student] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action="archive_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="permission_denied")
        return refused
    student = db.students.by_id(student_id)  # type: ignore[attr-defined]
    if student is None:
        note(deps, request_id, mark, action="archive_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="not_found")
        return Err("not_found", "not_found")
    if not can_archive(student.status):
        note(deps, request_id, mark, action="archive_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="validation_failed")
        return Err("validation_failed", "validation_failed")
    now = deps.clock.now()
    db.students.set_status(student_id, "archived", now)  # type: ignore[attr-defined]
    db.grants.revoke_student(student_id, now)  # type: ignore[attr-defined]
    saved = db.students.by_id(student_id)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="archive_student", actor=actor, target_kind="student", target_id=student_id, outcome="ok")
    return Ok(saved)


def list_students(db: object, actor: object) -> Ok[tuple[Student, ...]] | Err:
    refused = admin_only(actor)
    if refused is not None:
        return refused
    return Ok(db.students.list_all())  # type: ignore[attr-defined]
