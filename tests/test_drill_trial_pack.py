"""Safety checks for the trial-pack drill. The live round trip is not a unit test."""

from __future__ import annotations

import io
import os
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from backend.practice.domain.intake_image import image_kind, strip_jpeg_capture
from scripts.drill_trial_pack import guard, main, minimal_jpeg, refused_name

_ROOT = Path(__file__).resolve().parents[1]
_PLANTED = "drill-placeholder-value"
_DSN = "postgresql://k12:" + _PLANTED + "@127.0.0.1:5432/"
_DOCS = (
    _ROOT / "docs" / "ops" / "trial-handoff-checklist.md",
    _ROOT / "docs" / "ops" / "trial-recording-script.md",
)
_LEAK = re.compile(
    r"://[^/\s:]+:[^/\s@]+@|\bsk-[A-Za-z0-9]{8,}|\bAKIA[0-9A-Z]{16}|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY|api_key\s*[:=]\s*\S+",
    re.IGNORECASE,
)


class DrillGuardTest(unittest.TestCase):
    def test_refused_names(self) -> None:
        self.assertTrue(refused_name("k12"))
        self.assertTrue(refused_name("K12"))
        self.assertTrue(refused_name("postgres"))
        self.assertTrue(refused_name("k12_r11_src"))
        self.assertTrue(refused_name("k12_r11_dst"))
        self.assertFalse(refused_name("k12_d5_schema"))

    def test_empty_dsn_exits_2(self) -> None:
        code, out, err = _run([], {"K12_PG_DSN": ""})
        self.assertEqual(code, 2)
        self.assertIn("K12_PG_DSN is empty", err)
        self.assertNotIn(_PLANTED, out + err)

    def test_live_database_names_exit_2(self) -> None:
        for name in ("k12", "postgres", "k12_r11_src", "k12_r11_dst"):
            with self.subTest(name=name):
                code, out, err = _run([], {"K12_PG_DSN": _DSN + name})
                self.assertEqual(code, guard(_DSN + name, None))
                self.assertEqual(code, 2)
                self.assertIn("refusing database " + name, err)
                self.assertNotIn(_PLANTED, out + err)

    def test_port_8765_exits_2_without_leaking_the_password(self) -> None:
        code, out, err = _run(["--port", "8765"], {"K12_PG_DSN": _DSN + "k12_d5_schema"})
        self.assertEqual(code, 2)
        self.assertIn("8765", err)
        self.assertNotIn(_PLANTED, out + err)
        self.assertNotIn("k12_d5_schema", err)


class DrillJpegTest(unittest.TestCase):
    def test_minimal_jpeg_is_accepted_by_the_intake_checker(self) -> None:
        body = minimal_jpeg()
        self.assertTrue(body.startswith(b"\xff\xd8"))
        self.assertTrue(body.endswith(b"\xff\xd9"))
        self.assertEqual(image_kind(body), "jpeg")
        stripped = strip_jpeg_capture(body)
        self.assertEqual(image_kind(stripped), "jpeg")
        self.assertTrue(stripped.startswith(b"\xff\xd8"))
        self.assertTrue(stripped.endswith(b"\xff\xd9"))


class DrillHandoffDocTest(unittest.TestCase):
    def test_handoff_docs_exist_and_carry_no_real_book_or_secret(self) -> None:
        for path in _DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertGreater(len(text), 200)
            self.assertNotIn("课课练", text)
            self.assertIsNone(_LEAK.search(text), path.name)


def _run(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=False):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()
