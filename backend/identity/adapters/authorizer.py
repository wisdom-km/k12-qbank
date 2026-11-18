"""Practice calls allow(). This adapter does not import practice."""

from __future__ import annotations

from backend.identity.application.ports import GrantStore


class GrantAuthorizer:
    def __init__(self, grants: GrantStore) -> None:
        self._grants = grants

    def allow(self, teacher_id: str, student_id: str, subject_id: str) -> bool:
        return self._grants.active(teacher_id, student_id, subject_id) is not None
