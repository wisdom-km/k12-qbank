"""Grant and revoke a teacher, student, and subject. A repeat grant is the same row."""

from __future__ import annotations

import uuid

from backend.identity.application.conflict import Conflict
from backend.identity.application.deps import Deps
from backend.identity.application.guard import admin_only
from backend.identity.application.notes import note, started
from backend.identity.domain.records import Grant
from backend.identity.domain.rules import subject_ok
from backend.kernel.result import Err, Ok


def grant_teacher(db: object, actor: object, teacher_id: str, student_id: str, subject_id: str, deps: Deps, request_id: str) -> Ok[Grant] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        return _err(deps, request_id, mark, actor, "grant_teacher", "", "permission_denied")
    if not subject_ok(subject_id):
        return _err(deps, request_id, mark, actor, "grant_teacher", "", "validation_failed")
    teacher = db.users.by_id(teacher_id)  # type: ignore[attr-defined]
    student = db.students.by_id(student_id)  # type: ignore[attr-defined]
    if teacher is None or teacher.role != "teacher" or teacher.status != "active":
        return _err(deps, request_id, mark, actor, "grant_teacher", teacher_id, "not_found")
    if student is None or student.status != "active":
        return _err(deps, request_id, mark, actor, "grant_teacher", student_id, "not_found")
    existing = db.grants.active(teacher_id, student_id, subject_id)  # type: ignore[attr-defined]
    if existing is not None:
        note(deps, request_id, mark, action="grant_teacher", actor=actor, target_kind="grant", target_id=existing.grant_id, outcome="ok")
        return Ok(existing)
    now = deps.clock.now()
    grant = Grant(
        grant_id=str(uuid.uuid4()),
        teacher_id=teacher_id,
        student_id=student_id,
        subject_id=subject_id,
        granted_by=getattr(actor, "user_id", ""),
        granted_at=now,
    )
    try:
        db.grants.insert(grant)  # type: ignore[attr-defined]
    except Conflict as exc:
        note(deps, request_id, mark, action="grant_teacher", actor=actor, target_kind="grant", target_id="", outcome="err", reason_code=exc.code)
        raise
    note(deps, request_id, mark, action="grant_teacher", actor=actor, target_kind="grant", target_id=grant.grant_id, outcome="ok")
    return Ok(grant)


def revoke_grant(db: object, actor: object, teacher_id: str, student_id: str, subject_id: str, deps: Deps, request_id: str) -> Ok[Grant] | Err:
    mark = started()
    refused = admin_only(actor)
    if refused is not None:
        return _err(deps, request_id, mark, actor, "revoke_grant", "", "permission_denied")
    existing = db.grants.active(teacher_id, student_id, subject_id)  # type: ignore[attr-defined]
    if existing is None:
        return _err(deps, request_id, mark, actor, "revoke_grant", "", "not_granted")
    db.grants.revoke(existing.grant_id, deps.clock.now())  # type: ignore[attr-defined]
    saved = db.grants.by_id(existing.grant_id)  # type: ignore[attr-defined]
    note(deps, request_id, mark, action="revoke_grant", actor=actor, target_kind="grant", target_id=existing.grant_id, outcome="ok")
    return Ok(saved)


def list_grants(db: object, actor: object) -> Ok[tuple[Grant, ...]] | Err:
    refused = admin_only(actor)
    if refused is not None:
        return refused
    return Ok(db.grants.list_all())  # type: ignore[attr-defined]


def _err(deps: Deps, request_id: str, mark: float, actor: object, action: str, target_id: str, code: str) -> Err:
    kind = "grant"
    note(deps, request_id, mark, action=action, actor=actor, target_kind=kind, target_id=target_id, outcome="err", reason_code=code)
    return Err(code, code)
