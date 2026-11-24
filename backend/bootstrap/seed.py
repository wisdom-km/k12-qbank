"""Load the synthetic fixture into memory. The process starts unpublished."""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.bootstrap.compose import Loop
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.catalog.api import ApprovalSnapshot
from backend.identity.application.bootstrap_admin import bootstrap_admin
from backend.identity.application.run import execute
from backend.identity.application.synthetic_seed import seed_smoke_admin, seed_synthetic
from backend.kernel.result import Err

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "rational-number-min.json"


def synthetic_attempt_text() -> str:
    """The pending-answer text. It is not the catalog answer."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    text = data["pending_answer"]["text"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("synthetic attempt text is empty")
    if text == data["answer"]["text"]:
        raise ValueError("synthetic attempt text matches the catalog answer")
    return text


def load_fixture(loop: Loop) -> None:
    """Copy the fixture. Approval stays false until the teacher publishes.

    The JSON file still records the checked stem and answer. A second synthetic
    student is granted here so two papers can be issued. That student is not a
    seventh fixture block. production does not load this synthetic fixture.
    """
    if os.environ.get("K12_ENV", "").strip() == "production":
        return
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    question = data["question"]
    answer = data["answer"]
    paper = data["paper"]
    loop.approvals.put(
        ApprovalSnapshot(
            question_version_id=question["question_version_id"],
            answer_version_id=answer["answer_version_id"],
            asset_ids=tuple(paper["asset_ids"]),
            layout_template_id=paper["layout_template_id"],
            question_approved=False,
            answer_approved=False,
            retired=False,
            subject_id=question["subject_id"],
            item_order=tuple(paper["item_order"]),
            stem=question["stem"],
            answer_text=answer["text"],
        )
    )
    subject_id = question["subject_id"]
    students = (data["student"]["student_id"], "student-synth-2")
    _seed_identity(loop, subject_id, students)
    granter = getattr(loop.auth, "grant", None)
    if granter is not None:
        for student in students:
            granter(ACTOR_TEACHER_ID, student, subject_id)
    if os.environ.get("K12_PG_DSN", "").strip():
        return
    if os.environ.get("K12_BOOTSTRAP_ADMIN_USERNAME", "").strip():
        return
    _seed_smoke_admin(loop)


def _seed_identity(loop: Loop, subject_id: str, students: tuple[str, ...]) -> None:
    if loop.opener is None or loop.deps is None:
        return
    result = execute(
        loop.opener,  # type: ignore[arg-type]
        lambda db: seed_synthetic(
            db,
            loop.deps,  # type: ignore[arg-type]
            user_id=ACTOR_TEACHER_ID,
            username=ACTOR_TEACHER_ID,
            secret=SYNTH_SECRET,
            student_ids=students,
            subject_id=subject_id,
        ),
        loop.deps.logger,
        "seed",
    )
    if isinstance(result, Err):
        raise RuntimeError("synthetic seed failed")


def _seed_smoke_admin(loop: Loop) -> None:
    if loop.opener is None or loop.deps is None:
        return
    result = execute(
        loop.opener,  # type: ignore[arg-type]
        lambda db: seed_smoke_admin(
            db,
            loop.deps,  # type: ignore[arg-type]
            user_id=ACTOR_ADMIN_ID,
            username=ACTOR_ADMIN_ID,
            secret=SYNTH_SECRET,
            ),
        loop.deps.logger,
        "seed",
    )
    if isinstance(result, Err):
        raise RuntimeError("synthetic admin seed failed")


def bootstrap_from_env(loop: Loop) -> None:
    """Create the first admin when both env values are set. The secret is not logged."""
    username = os.environ.get("K12_BOOTSTRAP_ADMIN_USERNAME", "")
    secret = os.environ.get("K12_BOOTSTRAP_ADMIN_PASSWORD", "")
    if (not username and not secret) or loop.opener is None or loop.deps is None:
        return
    execute(
        loop.opener,  # type: ignore[arg-type]
        lambda db: bootstrap_admin(db, username, secret, loop.deps, "boot"),  # type: ignore[arg-type]
        loop.deps.logger,
        "boot",
    )
