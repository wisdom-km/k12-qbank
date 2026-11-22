"""Admin routes. Teachers receive permission_denied from the use cases."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.bootstrap.http_errors import error_response, run_use
from backend.bootstrap.schemas.publication import PublicationItem, PublicationListResponse
from backend.catalog.application.list_publications import bound_page, list_publications
from backend.catalog.application.publish_publication import publish_publication
from backend.catalog.application.retire_publication import retire_publication
from backend.identity.application.grants import grant_teacher, list_grants, revoke_grant
from backend.identity.application.guard import admin_only
from backend.identity.application.passwords import reset_teacher_password
from backend.identity.application.queries import list_audit_events
from backend.identity.application.students import archive_student, create_student, list_students
from backend.identity.application.sessions import revoke_all_sessions_for
from backend.identity.application.teachers import (
    create_teacher,
    disable_teacher,
    enable_teacher,
    list_teachers,
)
from backend.kernel.result import Err, StoreFault
from backend.kernel.use_log import emit


class TeacherBody(BaseModel):
    username: str
    secret: str


class SecretBody(BaseModel):
    secret: str


class StudentBody(BaseModel):
    name: str
    grade: str
    subject_id: str


class GrantBody(BaseModel):
    teacher_id: str
    student_id: str
    subject_id: str


class RetirePublicationBody(BaseModel):
    question_version_id: str
    answer_version_id: str


class PublishPublicationBody(BaseModel):
    question_version_id: str
    answer_version_id: str
    layout_template_id: str | None = None


def register_admin(app: FastAPI) -> None:
    @app.post("/api/admin/teachers")
    def teachers_create(body: TeacherBody, request: Request) -> JSONResponse:
        return _teacher_create(body, request)

    @app.get("/api/admin/teachers")
    def teachers_list(request: Request) -> JSONResponse:
        return _teachers(request)

    @app.post("/api/admin/teachers/{teacher_id}/disable")
    def teachers_disable(teacher_id: str, request: Request) -> JSONResponse:
        return _teacher_status(teacher_id, request, disable_teacher)

    @app.post("/api/admin/teachers/{teacher_id}/enable")
    def teachers_enable(teacher_id: str, request: Request) -> JSONResponse:
        return _teacher_status(teacher_id, request, enable_teacher)

    @app.post("/api/admin/teachers/{teacher_id}/password")
    def teachers_password(teacher_id: str, body: SecretBody, request: Request) -> JSONResponse:
        return _teacher_password(teacher_id, body, request)

    @app.post("/api/admin/students")
    def students_create(body: StudentBody, request: Request) -> JSONResponse:
        return _student_create(body, request)

    @app.get("/api/admin/students")
    def students_list(request: Request) -> JSONResponse:
        return _students(request)

    @app.post("/api/admin/students/{student_id}/archive")
    def students_archive(student_id: str, request: Request) -> JSONResponse:
        return _student_archive(student_id, request)

    @app.post("/api/admin/grants")
    def grants_create(body: GrantBody, request: Request) -> JSONResponse:
        return _grant(body, request)

    @app.post("/api/admin/grants/revoke")
    def grants_revoke(body: GrantBody, request: Request) -> JSONResponse:
        return _revoke(body, request)

    @app.get("/api/admin/grants")
    def grants_list(request: Request) -> JSONResponse:
        return _grants(request)

    @app.post("/api/admin/users/{user_id}/sessions/revoke")
    def user_sessions_revoke(user_id: str, request: Request) -> JSONResponse:
        return _user_sessions_revoke(user_id, request)

    @app.get("/api/admin/audit")
    def audit(request: Request, limit: int = 50, offset: int = 0, action: str = "", actor_user_id: str = "") -> JSONResponse:
        return _audit(request, limit, offset, action, actor_user_id)

    @app.get("/api/admin/publications", response_model=PublicationListResponse)
    def publications_list(
        request: Request,
        question_version_id: str | None = None,
        answer_version_id: str | None = None,
        subject_id: str | None = None,
        status: Literal["active", "retired"] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> JSONResponse:
        refused = admin_only(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        page_offset, page_limit = bound_page(offset, limit)
        rows, total = list_publications(
            request.app.state.loop.publications,
            question_version_id,
            answer_version_id,
            subject_id,
            status,
            page_offset,
            page_limit,
        )
        body = PublicationListResponse(
            items=[_publication_item(row) for row in rows],
            total=total,
            offset=page_offset,
            limit=page_limit,
        )
        return JSONResponse(body.model_dump())

    @app.post("/api/admin/publications/retire")
    def publications_retire(body: RetirePublicationBody, request: Request) -> JSONResponse:
        refused = admin_only(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        actor = request.state.actor.user_id
        started = time.perf_counter()
        try:
            code = retire_publication(
                request.app.state.loop.publications,
                body.question_version_id,
                body.answer_version_id,
                actor,
                request.app.state.loop.logger,
                request_id=request.state.request_id,
            )
        except StoreFault as fault:
            if fault.code != "invalid_actor":
                raise
            emit(
                request.app.state.loop.logger,
                level="ERROR",
                event="route_actor_missing",
                request_id=request.state.request_id,
                module="catalog.publication",
                outcome="invalid_actor",
                started=started,
            )
            return error_response(request.state.request_id, Err("store_failed", "store_failed"), status=500)
        if code == "not_found":
            return error_response(
                request.state.request_id,
                Err("not_found", "the publication binding does not exist"),
            )
        return JSONResponse({"outcome": code})

    @app.post("/api/admin/publications/publish")
    def publications_publish(body: PublishPublicationBody, request: Request) -> JSONResponse:
        refused = admin_only(request.state.actor)
        if refused is not None:
            return error_response(request.state.request_id, refused)
        actor = request.state.actor.user_id
        started = time.perf_counter()
        try:
            code = publish_publication(
                request.app.state.loop.publications,
                body.question_version_id,
                body.answer_version_id,
                actor,
                request.app.state.loop.logger,
                layout_template_id=body.layout_template_id,
                request_id=request.state.request_id,
            )
        except StoreFault as fault:
            if fault.code == "invalid_actor":
                emit(
                    request.app.state.loop.logger,
                    level="ERROR",
                    event="route_actor_missing",
                    request_id=request.state.request_id,
                    module="catalog.publication",
                    outcome="invalid_actor",
                    started=started,
                )
                return error_response(request.state.request_id, Err("store_failed", "store_failed"), status=500)
            if fault.code == "invalid_subject":
                emit(
                    request.app.state.loop.logger,
                    level="ERROR",
                    event="route_subject_missing",
                    request_id=request.state.request_id,
                    module="catalog.publication",
                    outcome="invalid_subject",
                    started=started,
                )
                return error_response(request.state.request_id, Err("store_failed", "store_failed"), status=500)
            raise
        if code == "not_approved":
            return error_response(
                request.state.request_id,
                Err("not_approved", "the question and answer are not both approved"),
            )
        if code == "published":
            rows = request.app.state.loop.publications.rows_for(
                body.question_version_id,
                body.answer_version_id,
            )
            active = [row for row in rows if row.status == "active"]
            return JSONResponse(
                {"outcome": "published", "publication_id": active[0].publication_id}
            )
        return JSONResponse({"outcome": "already_active"})


def _teacher_create(body: TeacherBody, request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: create_teacher(db, actor, body.username, body.secret, deps, request.state.request_id),
    )
    return _user_result(request, result)


def _teachers(request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(request, lambda db: list_teachers(db, actor, deps, request.state.request_id))
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"teachers": [_user_body(user) for user in result.value]})


def _teacher_status(teacher_id: str, request: Request, command: object) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: command(db, actor, teacher_id, deps, request.state.request_id),  # type: ignore[operator]
    )
    return _user_result(request, result)


def _teacher_password(teacher_id: str, body: SecretBody, request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: reset_teacher_password(db, actor, teacher_id, body.secret, deps, request.state.request_id),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"ok": True})


def _user_sessions_revoke(user_id: str, request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: revoke_all_sessions_for(db, actor, user_id, deps, request.state.request_id),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"revoked": result.value})


def _student_create(body: StudentBody, request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: create_student(db, actor, body.name, body.grade, body.subject_id, deps, request.state.request_id),
    )
    return _student_result(request, result)


def _students(request: Request) -> JSONResponse:
    result = run_use(request, lambda db: list_students(db, request.state.actor))
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"students": [_student_body(row) for row in result.value]})


def _student_archive(student_id: str, request: Request) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: archive_student(db, actor, student_id, deps, request.state.request_id),
    )
    return _student_result(request, result)


def _grant(body: GrantBody, request: Request) -> JSONResponse:
    return _grant_call(body, request, grant_teacher)


def _revoke(body: GrantBody, request: Request) -> JSONResponse:
    return _grant_call(body, request, revoke_grant)


def _grant_call(body: GrantBody, request: Request, command: object) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: command(  # type: ignore[operator]
            db, actor, body.teacher_id, body.student_id, body.subject_id, deps, request.state.request_id
        ),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse(_grant_body(result.value))


def _grants(request: Request) -> JSONResponse:
    result = run_use(request, lambda db: list_grants(db, request.state.actor))
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse({"grants": [_grant_body(row) for row in result.value]})


def _audit(request: Request, limit: int, offset: int, action: str, actor_user_id: str) -> JSONResponse:
    actor = request.state.actor
    deps = request.app.state.deps
    result = run_use(
        request,
        lambda db: list_audit_events(
            db,
            actor,
            deps,
            request.state.request_id,
            limit=limit,
            offset=offset,
            action=action,
            actor_user_id=actor_user_id,
            since=None,
            until=None,
        ),
    )
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    rows, total = result.value  # type: ignore[misc]
    return JSONResponse({"total": total, "events": [_audit_body(row) for row in rows]})


def _user_result(request: Request, result: object) -> JSONResponse:
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse(_user_body(result.value))  # type: ignore[attr-defined]


def _student_result(request: Request, result: object) -> JSONResponse:
    if isinstance(result, Err):
        return error_response(request.state.request_id, result)
    return JSONResponse(_student_body(result.value))  # type: ignore[attr-defined]


def _user_body(user: object) -> dict[str, object]:
    return {
        "user_id": user.user_id,  # type: ignore[attr-defined]
        "username": user.username,  # type: ignore[attr-defined]
        "role": user.role,  # type: ignore[attr-defined]
        "status": user.status,  # type: ignore[attr-defined]
    }


def _student_body(student: object) -> dict[str, object]:
    return {
        "student_id": student.student_id,  # type: ignore[attr-defined]
        "name": student.name,  # type: ignore[attr-defined]
        "grade": student.grade,  # type: ignore[attr-defined]
        "subject_id": student.subject_id,  # type: ignore[attr-defined]
        "status": student.status,  # type: ignore[attr-defined]
    }


def _grant_body(grant: object) -> dict[str, object]:
    return {
        "grant_id": grant.grant_id,  # type: ignore[attr-defined]
        "teacher_id": grant.teacher_id,  # type: ignore[attr-defined]
        "student_id": grant.student_id,  # type: ignore[attr-defined]
        "subject_id": grant.subject_id,  # type: ignore[attr-defined]
        "revoked": grant.revoked_at is not None,  # type: ignore[attr-defined]
    }


def _publication_item(row: object) -> PublicationItem:
    return PublicationItem(
        publication_id=row.publication_id,  # type: ignore[attr-defined]
        question_version_id=row.question_version_id,  # type: ignore[attr-defined]
        answer_version_id=row.answer_version_id,  # type: ignore[attr-defined]
        subject_id=row.subject_id,  # type: ignore[attr-defined]
        status=row.status,  # type: ignore[attr-defined]
        layout_template_id=row.layout_template_id,  # type: ignore[attr-defined]
    )


def _audit_body(row: object) -> dict[str, object]:
    return {
        "occurred_at": row.occurred_at.isoformat(),  # type: ignore[attr-defined]
        "request_id": row.request_id,  # type: ignore[attr-defined]
        "actor_user_id": row.actor_user_id,  # type: ignore[attr-defined]
        "actor_role": row.actor_role,  # type: ignore[attr-defined]
        "action": row.action,  # type: ignore[attr-defined]
        "target_kind": row.target_kind,  # type: ignore[attr-defined]
        "target_id": row.target_id,  # type: ignore[attr-defined]
        "reason_code": row.reason_code,  # type: ignore[attr-defined]
        "outcome": row.outcome,  # type: ignore[attr-defined]
    }
