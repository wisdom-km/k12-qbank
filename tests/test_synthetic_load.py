"""production does not load the synthetic fixture. development still does."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from backend.bootstrap.compose import compose
from backend.bootstrap.seed import load_fixture
from backend.bootstrap.synthetic import SYNTH_SECRET
from backend.identity.domain.rules import password_ok


class SyntheticLoadTest(unittest.TestCase):
    def test_development_loads_the_synthetic_teacher(self) -> None:
        with mock.patch.dict(os.environ, {"K12_ENV": "development"}):
            loop = compose()
            load_fixture(loop)
        self.assertIsNotNone(loop.identity.users.by_username("teacher-synth"))  # type: ignore[attr-defined]
        self.assertIsNotNone(loop.approvals.read_snapshot("q-v1"))

    def test_production_skips_the_synthetic_fixture(self) -> None:
        with mock.patch.dict(os.environ, {"K12_ENV": "production"}):
            loop = compose()
            load_fixture(loop)
        self.assertIsNone(loop.identity.users.by_username("teacher-synth"))  # type: ignore[attr-defined]
        self.assertIsNone(loop.approvals.read_snapshot("q-v1"))

    def test_default_synthetic_secret_meets_the_password_rule(self) -> None:
        self.assertTrue(password_ok(SYNTH_SECRET))
        self.assertNotIn(" ", SYNTH_SECRET)

    def test_development_seeds_the_smoke_admin_when_no_dsn_and_no_bootstrap_user(self) -> None:
        env = {"K12_ENV": "development", "K12_PG_DSN": "", "K12_BOOTSTRAP_ADMIN_USERNAME": ""}
        with mock.patch.dict(os.environ, env):
            loop = compose()
            load_fixture(loop)
        self.assertIsNotNone(loop.identity.users.by_username("admin-synth"))  # type: ignore[attr-defined]

    def test_bootstrap_username_skips_the_smoke_admin(self) -> None:
        env = {"K12_ENV": "development", "K12_PG_DSN": "", "K12_BOOTSTRAP_ADMIN_USERNAME": "admin"}
        with mock.patch.dict(os.environ, env):
            loop = compose()
            load_fixture(loop)
        self.assertIsNone(loop.identity.users.by_username("admin-synth"))  # type: ignore[attr-defined]
        self.assertIsNotNone(loop.identity.users.by_username("teacher-synth"))  # type: ignore[attr-defined]
