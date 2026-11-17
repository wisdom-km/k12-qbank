"""Papers and official records the server teacher is allowed to see."""

from __future__ import annotations

from backend.practice.application.ports import Authorizer, PracticeStore
from backend.practice.domain.paper import Paper


def visible_papers(
    actor_teacher_id: str,
    auth: Authorizer,
    store: PracticeStore,
) -> tuple[Paper, ...]:
    """Keep papers owned by this teacher and allowed for that student and subject."""
    return tuple(
        paper
        for paper in store.list_papers()
        if paper.teacher_id == actor_teacher_id
        and auth.allow(actor_teacher_id, paper.student_id, paper.subject_id)
    )


def visible_confirmation_count(
    actor_teacher_id: str,
    auth: Authorizer,
    store: PracticeStore,
) -> int:
    """Count official rows for this teacher on papers that teacher may see."""
    allowed = {paper.paper_id for paper in visible_papers(actor_teacher_id, auth, store)}
    return sum(
        1
        for row in store.list_confirmations()
        if row.teacher_id == actor_teacher_id and row.paper_id in allowed
    )
