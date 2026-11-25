"""production does not load the synthetic fixture or the synthetic accounts."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from backend.bootstrap.compose import compose
from backend.bootstrap.seed import load_fixture
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, STUDENT_IDS


class TrialSeedTest(unittest.TestCase):
    def test_production_leaves_the_memory_loop_without_synthetic_rows(self) -> None:
        with mock.patch.dict(os.environ, {"K12_ENV": "production"}):
            loop = compose()
            load_fixture(loop)
        self.assertEqual(loop.approvals.list_snapshots(), ())  # type: ignore[attr-defined]
        identity = loop.identity
        assert identity is not None
        users = identity.users.list_role("teacher") + identity.users.list_role("admin")  # type: ignore[attr-defined]
        names = {user.user_id for user in users}
        self.assertNotIn(ACTOR_TEACHER_ID, names)
        self.assertNotIn(ACTOR_ADMIN_ID, names)
        for student_id in STUDENT_IDS:
            self.assertIsNone(identity.students.by_id(student_id))  # type: ignore[attr-defined]
