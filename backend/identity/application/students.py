"""Admin creates and updates students. Names and external ids stay out of the audit row."""

from __future__ import annotations

import uuid

from backend.identity.application.conflict import Conflict
from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.application.notes import note, started
from backend.identity.domain.records import Student
from backend.identity.domain.rules import can_archive, external_id_ok, label_ok, subject_ok
from backend.kernel.result import Err, Ok


def create_student(
    db: object,
    actor: object,
    external_id: str,
    grade: str,
    subject_id: str,
    deps: Deps,
    request_id: str,
    name: str | None = None,
) -> Ok[Student] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id="", outcome="err", reason_code="permission_denied")
        return refused
    stored_name = _stored_name(name)
    cleaned = external_id.strip()
    if stored_name is None or not external_id_ok(cleaned) or not label_ok(grade, 32) or not subject_ok(subject_id):
        note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id="", outcome="err", reason_code="validation_failed")
        return Err("validation_failed", "validation_failed")
    if db.students.by_external_id(cleaned) is not None:  # type: ignore[attr-defined]
        note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id="", outcome="err", reason_code="external_id_taken")
        return Err("external_id_taken", "external_id_taken")
    now = deps.clock.now()
    student = Student(
        student_id=str(uuid.uuid4()),
        external_id=cleaned,
        name=stored_name,
        grade=grade.strip(),
        subject_id=subject_id,
        status="active",
        created_by=getattr(actor, "user_id", ""),
        created_at=now,
        updated_at=now,
    )
    try:
        db.students.insert(student)  # type: ignore[attr-defined]
    except Conflict as exc:
        note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id="", outcome="err", reason_code=exc.code)
        raise
    note(deps, request_id, mark, action="create_student", actor=actor, target_kind="student", target_id=student.student_id, outcome="ok")
    return Ok(student)


def update_student(
    db: object,
    actor: object,
    student_id: str,
    external_id: str,
    grade: str,
    subject_id: str,
    deps: Deps,
    request_id: str,
    name: str | None = None,
) -> Ok[Student] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        note(deps, request_id, mark, action="update_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="permission_denied")
        return refused
    current = db.students.by_id(student_id)  # type: ignore[attr-defined]
    if current is None:
        note(deps, request_id, mark, action="update_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="not_found")
        return Err("not_found", "not_found")
    stored_name = current.name if name is None else _stored_name(name)
    cleaned = external_id.strip()
    if stored_name is None or not external_id_ok(cleaned) or not label_ok(grade, 32) or not subject_ok(subject_id):
        note(deps, request_id, mark, action="update_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="validation_failed")
        return Err("validation_failed", "validation_failed")
    other = db.students.by_external_id(cleaned)  # type: ignore[attr-defined]
    if other is not None and other.student_id != student_id:
        note(deps, request_id, mark, action="update_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code="external_id_taken")
        return Err("external_id_taken", "external_id_taken")
    now = deps.clock.now()
    saved = Student(
        student_id=current.student_id,
        external_id=cleaned,
        name=stored_name,
        grade=grade.strip(),
        subject_id=subject_id,
        status=current.status,
        created_by=current.created_by,
        created_at=current.created_at,
        updated_at=now,
    )
    try:
        db.students.update(saved)  # type: ignore[attr-defined]
    except Conflict as exc:
        note(deps, request_id, mark, action="update_student", actor=actor, target_kind="student", target_id=student_id, outcome="err", reason_code=exc.code)
        raise
    note(deps, request_id, mark, action="update_student", actor=actor, target_kind="student", target_id=student_id, outcome="ok")
    return Ok(saved)


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


def list_visible_students(db: object, actor: object) -> Ok[tuple[Student, ...]] | Err:
    role = str(getattr(actor, "role", ""))
    if role == "admin":
        return Ok(db.students.list_all())  # type: ignore[attr-defined]
    if role != "teacher":
        return Err("permission_denied", "permission_denied")
    teacher_id = str(getattr(actor, "user_id", ""))
    rows = tuple(student for student in db.students.list_all() if _granted(db, teacher_id, student.student_id))  # type: ignore[attr-defined]
    return Ok(rows)


def get_visible_student(db: object, actor: object, student_id: str) -> Ok[Student] | Err:
    role = str(getattr(actor, "role", ""))
    student = db.students.by_id(student_id)  # type: ignore[attr-defined]
    if role == "admin":
        if student is None:
            return Err("not_found", "not_found")
        return Ok(student)
    if role != "teacher":
        return Err("permission_denied", "permission_denied")
    teacher_id = str(getattr(actor, "user_id", ""))
    if student is None or not _granted(db, teacher_id, student_id):
        return Err("not_found", "not_found")
    return Ok(student)


def _stored_name(name: str | None) -> str | None:
    if name is None or not name.strip():
        return ""
    text = name.strip()
    if not label_ok(text, 80):
        return None
    return text


def _granted(db: object, teacher_id: str, student_id: str) -> bool:
    for grant in db.grants.list_all():  # type: ignore[attr-defined]
        if grant.teacher_id == teacher_id and grant.student_id == student_id and grant.revoked_at is None:
            return True
    return False
