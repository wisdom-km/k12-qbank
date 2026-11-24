"""The import script reads the current role and does not keep secrets in the report."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from scripts.import_book import build_body, build_request

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "synth-book-roles"
LOGIN_MARKER = "pw-marker-r4c1"
CSRF = "csrf-marker-r4c"
SESSION = "sid-marker-r4c"


class ImportBookScriptReadTest(unittest.TestCase):
    def test_reader_keeps_only_the_current_role(self) -> None:
        book_id, body = build_request(str(FIXTURE))
        self.assertEqual(book_id, "synth-roles")
        self.assertEqual(body["pairing"], [{"answer_page": 101, "question_page": 12}])
        pages = body["pages"]
        self.assertEqual([page["pdf_page"] for page in pages], [7, 12, 101])
        self.assertEqual([page["role"] for page in pages], ["questions", "questions", "answers"])
        self.assertEqual(pages[0]["answers"], [])
        self.assertEqual(pages[1]["answers"], [])
        text = json.dumps(body, ensure_ascii=False)
        self.assertIn("synth-q-7", text)
        self.assertIn("synth-q-12", text)
        self.assertIn("synth-a-101", text)
        self.assertNotIn("synth-leftover-answer-12", text)
        self.assertNotIn("synth-leftover-q-101", text)
        self.assertNotIn("synth-leftover-answer-7", text)
        self.assertNotIn("synth-backup", text)
        self.assertNotIn("synth-reviewed", text)
        self.assertNotIn("synth-hidden", text)

    def test_unknown_manifest_fields_are_forwarded(self) -> None:
        body = build_body(
            {"book_id": "synth-roles", "subject_id": "math", "pairs": [], "answer_box": 1},
            [],
            dry_run=True,
        )
        self.assertEqual(body["answer_box"], 1)
        self.assertNotIn("book_id", body)

    def test_source_does_not_import_the_server_package(self) -> None:
        source = Path(__file__).resolve().parents[1].joinpath("scripts", "import_book.py").read_text(encoding="utf-8")
        self.assertNotIn("backend", source)


class ImportBookScriptHttpTest(unittest.TestCase):
    def test_dry_run_report_omits_the_password_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = _copy_book(Path(raw))
            server = _listen(_ok)
            try:
                code = _invoke(folder, server)
            finally:
                _stop(server)
            self.assertEqual(code, 0)
            reports = list((folder / "_import_reports").glob("import-synth-roles-*.json"))
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8") + reports[0].with_suffix(".txt").read_text(encoding="utf-8")
            self.assertNotIn(LOGIN_MARKER, text)
            self.assertNotIn(CSRF, text)
            self.assertNotIn(SESSION, text)
            self.assertIn("synth-roles", text)

    def test_password_change_then_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = _copy_book(Path(raw))
            server = _listen(_change)
            try:
                code = _invoke(folder, server)
            finally:
                _stop(server)
            self.assertEqual(code, 0)
            self.assertTrue(server.changed)  # type: ignore[attr-defined]


def _ok(handler: BaseHTTPRequestHandler, payload: dict[str, object]) -> None:
    if handler.path == "/api/login":
        _send(handler, 200, {"csrf_token": CSRF, "user_id": "admin-synth"}, cookie=True)
        return
    if handler.path == "/api/catalog":
        _send(handler, 200, {"items": []})
        return
    if handler.path.startswith("/api/admin/catalog/books/") and payload.get("dry_run") is True:
        _send(
            handler,
            200,
            {
                "book_id": "synth-roles",
                "dry_run": True,
                "written": False,
                "reason": "",
                "pages": [{"pdf_page": 12, "role": "questions", "outcome": "ok", "reason": ""}],
                "questions": [
                    {
                        "original_key": "1:1",
                        "key": "synth-roles.p0012:1:1",
                        "question_version_id": "qv-synth-roles.p0012-1-1",
                        "outcome": "staged",
                        "reason": "",
                    }
                ],
                "staged": 1,
                "kept": 0,
                "skipped": 0,
                "conflict": 0,
            },
        )
        return
    _send(handler, 404, {"code": "not_found"})


def _change(handler: BaseHTTPRequestHandler, payload: dict[str, object]) -> None:
    if handler.path == "/api/login":
        _send(handler, 200, {"csrf_token": CSRF, "user_id": "admin-synth"}, cookie=True)
        return
    if handler.path == "/api/catalog":
        _send(handler, 403, {"code": "password_change_required"})
        return
    if handler.path == "/api/account/password":
        handler.server.changed = True  # type: ignore[attr-defined]
        _send(handler, 200, {"ok": True})
        return
    if handler.path.startswith("/api/admin/catalog/books/"):
        _send(
            handler,
            200,
            {
                "book_id": "synth-roles",
                "dry_run": True,
                "written": False,
                "reason": "",
                "pages": [],
                "questions": [],
                "staged": 0,
                "kept": 0,
                "skipped": 0,
                "conflict": 0,
            },
        )
        return
    _send(handler, 404, {"code": "not_found"})


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.server.dispatch(self, {})  # type: ignore[attr-defined]

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        self.server.dispatch(self, payload)  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        return


def _send(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, object], cookie: bool = False) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if cookie:
        handler.send_header("Set-Cookie", "k12_sid=" + SESSION + "; HttpOnly; Path=/")
    handler.end_headers()
    handler.wfile.write(body)


def _listen(dispatch: object) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.dispatch = dispatch  # type: ignore[attr-defined]
    server.changed = False  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.thread = thread  # type: ignore[attr-defined]
    thread.start()
    return server


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.thread.join(2)  # type: ignore[attr-defined]
    server.server_close()


def _url(server: ThreadingHTTPServer) -> str:
    return "http://127.0.0.1:" + str(server.server_address[1])


def _copy_book(folder: Path) -> Path:
    target = folder / "book"
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("_import_reports"))
    return target


class _Stdin:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def isatty(self) -> bool:
        return False

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0) + "\n"


def _invoke(folder: Path, server: ThreadingHTTPServer) -> int:
    from scripts import import_book as script

    stdin = _Stdin([LOGIN_MARKER, "next-marker-r4c1", "next-marker-r4c1"])
    with mock.patch.dict(os.environ, {"K12_IMPORT_USER": "admin-synth"}):
        with mock.patch.object(script.sys, "stdin", stdin):
            return script.main(["--book-dir", str(folder), "--server", _url(server), "--dry-run-only"])
