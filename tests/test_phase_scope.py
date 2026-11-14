"""Phase list, fixed health body, and the synthetic fixture shape."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from backend.bootstrap.compose import compose
from backend.bootstrap.health import health_report

ROOT = Path(__file__).resolve().parents[1]


def boundaries():
    path = ROOT / "scripts" / "check_boundaries.py"
    spec = importlib.util.spec_from_file_location("check_boundaries", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_boundaries")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PhaseScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bounds = boundaries()

    def test_blank_list_uses_catalog_and_practice(self) -> None:
        allowed, error, source = self.bounds.resolve_phase_slices("", None)
        self.assertEqual(error, "")
        self.assertEqual(source, "default")
        self.assertEqual(allowed, frozenset({"catalog", "practice"}))

    def test_env_overrides_conf(self) -> None:
        allowed, error, source = self.bounds.resolve_phase_slices(
            "catalog practice", "catalog"
        )
        self.assertEqual(error, "")
        self.assertEqual(source, "env")
        self.assertEqual(allowed, frozenset({"catalog"}))

    def test_unknown_slice_is_refused(self) -> None:
        allowed, error, source = self.bounds.resolve_phase_slices("", "catalog nosuch")
        self.assertIsNone(allowed)
        self.assertIn("nosuch", error)
        self.assertEqual(source, "env")

    def test_default_check_passes(self) -> None:
        result = self._run_check(None)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("phase scope (catalog practice, from check.conf)", result.stdout)

    def test_narrow_env_refuses_practice(self) -> None:
        result = self._run_check("catalog")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("F-13", result.stdout)
        self.assertIn("backend/practice", result.stdout)
        self.assertIn("from env", result.stdout)

    def test_health_body_is_status_only(self) -> None:
        report = health_report()
        self.assertEqual(report.status, "ok")
        self.assertEqual(set(report.__dataclass_fields__), {"status"})
        self.assertEqual(compose().health, report)

    def test_fixture_has_five_blocks_and_no_image(self) -> None:
        path = ROOT / "docs" / "fixtures" / "rational-number-min.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(data),
            {"question", "answer", "student", "paper", "photo_version"},
        )
        self.assertEqual(data["question"]["question_version_id"], "q-v1")
        self.assertEqual(data["answer"]["answer_version_id"], "a-v1")
        self.assertEqual(data["student"], {"student_id": "student-synth"})
        self.assertEqual(data["paper"]["question_version_id"], "q-v1")
        self.assertFalse(data["photo_version"]["contains_image_bytes"])

    def _run_check(self, phase: str | None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PHASE_SLICES", None)
        if phase is not None:
            env["PHASE_SLICES"] = phase
        return subprocess.run(
            [sys.executable, "scripts/check_boundaries.py"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
