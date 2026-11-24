"""Server-side synthetic identity. The HTTP body does not choose the actor."""

from __future__ import annotations

import os

ACTOR_TEACHER_ID = "teacher-synth"
ACTOR_ADMIN_ID = "admin-synth"
SYNTH_SECRET = os.environ.get("K12_SYNTH_SECRET", "synth-pass1-dev-only")
QUESTION_VERSION_ID = "q-v1"
REVIEW_VERSION_ID = "rev-1"
STUDENT_IDS = ("student-synth", "student-synth-2")
