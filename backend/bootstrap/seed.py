"""Load the synthetic fixture into memory. The process starts unpublished."""

from __future__ import annotations

import json
from pathlib import Path

from backend.bootstrap.compose import Loop
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID
from backend.catalog.api import ApprovalSnapshot

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "rational-number-min.json"


def load_fixture(loop: Loop) -> None:
    """Copy the fixture. Approval stays false until the teacher publishes.

    The JSON file still records the checked stem and answer. A second synthetic
    student is granted here so two papers can be issued. That student is not a
    seventh fixture block.
    """
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
    for student in students:
        loop.auth.grant(ACTOR_TEACHER_ID, student, subject_id)
