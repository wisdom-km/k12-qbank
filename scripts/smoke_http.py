"""One business smoke against a running synthetic server. Not a unit test."""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET  # noqa: E402


def main() -> int:
    port = os.environ.get("K12_PORT", "8765")
    base = "http://127.0.0.1:" + port
    health = _json(_open(base + "/health"))
    if health.get("status") != "ok" or set(health) != {"status"}:
        print("SMOKE HTTP FAIL: health " + json.dumps(health, ensure_ascii=False))
        return 1
    _CSRF["value"] = _login(base)
    issue = {
        "teacher_id": "teacher-synth",
        "student_id": "student-synth",
        "subject_id": "math",
        "question_version_id": "q-v1",
        "review_version_id": "rev-1",
    }
    refused = _json(_open(base + "/api/practice/papers", issue, expect=409))
    if refused.get("code") != "not_approved":
        print("SMOKE HTTP FAIL: expected not_approved, got " + json.dumps(refused, ensure_ascii=False))
        return 1
    papers = _json(_open(base + "/api/practice/papers"))
    if papers.get("count") != 0:
        print("SMOKE HTTP FAIL: refusal wrote a paper")
        return 1
    published = _json(_open(base + "/api/catalog/q-v1/publish", {}))
    if not published.get("question_approved") or not published.get("answer_approved"):
        print("SMOKE HTTP FAIL: publish did not approve")
        return 1
    opened = _json(_open(base + "/api/practice/papers", issue))
    if opened.get("status") != "可打印" or not opened.get("file_id") or not opened.get("file_checksum"):
        print("SMOKE HTTP FAIL: issue " + json.dumps(opened, ensure_ascii=False))
        return 1
    pdf = _open(base + "/api/practice/files/" + str(opened["file_id"])).read()
    paper_id = str(opened["paper_id"]).encode()
    if (
        b"\\(-3\\)+5" not in pdf
        or b"<8BA1>" not in pdf
        or b"synth-0001" not in pdf
        or b"<7B2C>" not in pdf
        or b"<9875>" not in pdf
        or b"<5171>" not in pdf
        or b"page 1" in pdf
        or b"pages 1" in pdf
    ):
        print("SMOKE HTTP FAIL: pdf missing stem, external id, or page label")
        return 1
    if b"student-synth" in pdf or b"name-rule omit" in pdf or paper_id in pdf or b"answer " in pdf:
        print("SMOKE HTTP FAIL: pdf prints the internal id, a name rule, the paper id, or an answer")
        return 1
    if b"\\frac" in pdf or b"\\times" in pdf or b"\\leq" in pdf:
        print("SMOKE HTTP FAIL: pdf prints a latex command")
        return 1
    if _intake(base, str(opened["paper_id"])) != 0:
        return 1
    refused_import = _json(
        _open(base + "/api/admin/catalog/books/synth-smoke/import", _smoke_page(True), expect=403)
    )
    if refused_import.get("code") != "permission_denied":
        print("SMOKE HTTP FAIL: teacher import code " + str(refused_import.get("code")))
        return 1
    _CSRF["value"] = _login(base, ACTOR_ADMIN_ID)
    dry = _json(_open(base + "/api/admin/catalog/books/synth-smoke/import", _smoke_page(True)))
    if dry.get("written") is not False or int(dry.get("staged") or 0) < 1 or dry.get("reason"):
        print(_smoke_fail("dry_run", dry))
        return 1
    saved = _json(_open(base + "/api/admin/catalog/books/synth-smoke/import", _smoke_page(False)))
    if saved.get("written") is not True or int(saved.get("staged") or 0) < 1 or saved.get("reason"):
        print(_smoke_fail("write", saved))
        return 1
    again = _json(_open(base + "/api/admin/catalog/books/synth-smoke/import", _smoke_page(False)))
    if (
        again.get("written") is not True
        or int(again.get("kept") or 0) < 1
        or int(again.get("staged") or 0) != 0
        or again.get("reason")
    ):
        print(_smoke_fail("rerun", again))
        return 1
    print("SMOKE HTTP PASS")
    return 0


def _intake(base: str, paper_id: str) -> int:
    """Upload one synthetic page, read the status, then read the image once."""
    uploaded = _json(
        _put_bytes(
            base + "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
            _jpeg(),
        )
    )
    intake_id = uploaded.get("intake_id")
    if not isinstance(intake_id, str) or not intake_id.startswith("intake-"):
        print("SMOKE HTTP FAIL: intake upload")
        return 1
    status = _json(_open(base + "/api/practice/papers/" + paper_id + "/intake"))
    pages = status.get("pages")
    if not isinstance(pages, list) or not pages or not pages[0].get("received"):
        print("SMOKE HTTP FAIL: intake status")
        return 1
    image = _open(base + "/api/practice/intake/" + intake_id + "/image")
    body = image.read()
    if image.headers.get("Cache-Control") != "no-store" or not body.startswith(b"\xff\xd8"):
        print("SMOKE HTTP FAIL: intake image")
        return 1
    if b"EXIF-MARKER-SYNTH" in body or b"student-synth" in body or b"synth-0001" in body:
        print("SMOKE HTTP FAIL: intake image still has capture data or an id")
        return 1
    started = _json(_open(base + "/api/practice/intake/" + intake_id + "/ai-runs", {}, 202))
    run_id = started.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith("run-"):
        print("SMOKE HTTP FAIL: ai run")
        return 1
    deadline = time.time() + 5
    report: dict[str, object] = {}
    while time.time() < deadline:
        report = _json(_open(base + "/api/practice/ai-runs/" + run_id))
        if report.get("status") in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    if report.get("status") != "succeeded":
        print("SMOKE HTTP FAIL: ai status " + str(report.get("status")) + " " + str(report.get("error_code")))
        return 1
    suggestions = report.get("suggestions")
    if not isinstance(suggestions, list) or not suggestions:
        print("SMOKE HTTP FAIL: ai suggestions")
        return 1
    return 0


def _jpeg() -> bytes:
    payload = b"EXIF-MARKER-SYNTH"
    length = len(payload) + 2
    segment = bytes((0xFF, 0xE1, (length >> 8) & 0xFF, length & 0xFF)) + payload
    return b"\xff\xd8" + segment + bytes((0xFF, 0xDA, 0x00, 0x02)) + b"IMAGE-BYTES-SYNTH" + b"\xff\xd9"


def _put_bytes(url: str, body: bytes, expect: int = 200) -> urllib.response.addinfourl:
    headers = {
        "Content-Type": "image/jpeg",
        "X-Request-Id": "smoke-http",
        "X-K12-CSRF": _CSRF["value"],
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="PUT")
    try:
        response = _OPENER.open(request, timeout=3)
    except urllib.error.HTTPError as exc:
        if exc.code != expect:
            print("SMOKE HTTP FAIL: " + url + " status " + str(exc.code))
            print(exc.read().decode("utf-8", errors="replace"))
            raise SystemExit(1) from exc
        return exc
    if response.status != expect:
        print("SMOKE HTTP FAIL: " + url + " status " + str(response.status))
        raise SystemExit(1)
    return response


def _smoke_fail(step: str, report: dict[str, object]) -> str:
    return (
        "SMOKE HTTP FAIL: "
        + step
        + " staged="
        + str(report.get("staged"))
        + " kept="
        + str(report.get("kept"))
        + " written="
        + str(report.get("written"))
        + " reason="
        + str(report.get("reason"))
    )


def _smoke_page(dry_run: bool) -> dict[str, object]:
    question = {
        "contract": "k12-question-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "preface": "",
        "source": {"pdf_page": 1},
        "questions": [
            {
                "key": "1:1",
                "section": "一",
                "number": "1",
                "type": "single_choice",
                "structure": "choice",
                "status": "confirmed",
                "stem": [{"type": "text", "value": "synth-smoke"}],
                "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
                "subquestions": [],
                "assets": [],
                "geometry": None,
            }
        ],
    }
    answer = {
        "contract": "k12-answer-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "question_key": "1:1",
        "key": "1:1:ocr:1",
        "origin": "ocr",
        "status": "confirmed",
        "applicable": True,
        "source": {"pdf_page": 1},
        "content": [{"type": "text", "value": "synth-smoke-a"}],
        "parts": [],
        "assets": [],
    }
    return {
        "subject_id": "math",
        "dry_run": dry_run,
        "pages": [{"pdf_page": 1, "role": "questions", "questions": question, "answers": [answer]}],
        "pairing": [],
    }


def _login(base: str, username: str = ACTOR_TEACHER_ID) -> str:
    body = _json(_open(base + "/api/login", {"username": username, "secret": SYNTH_SECRET}))
    token = body.get("csrf_token")
    if not isinstance(token, str) or not token:
        print("SMOKE HTTP FAIL: login did not return a csrf token")
        raise SystemExit(1)
    return token


def _open(url: str, body: dict[str, object] | None = None, expect: int = 200) -> urllib.response.addinfourl:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Request-Id": "smoke-http"}
    if body is not None and _CSRF["value"] and not url.endswith("/api/login"):
        headers["X-K12-CSRF"] = _CSRF["value"]
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    try:
        response = _OPENER.open(request, timeout=3)
    except urllib.error.HTTPError as exc:
        if exc.code != expect:
            print("SMOKE HTTP FAIL: " + url + " status " + str(exc.code))
            print(exc.read().decode("utf-8", errors="replace"))
            raise SystemExit(1) from exc
        return exc
    if response.status != expect:
        print("SMOKE HTTP FAIL: " + url + " status " + str(response.status))
        raise SystemExit(1)
    return response


def _json(response: urllib.response.addinfourl) -> dict[str, object]:
    return json.loads(response.read().decode("utf-8"))


_CSRF = {"value": ""}
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


if __name__ == "__main__":
    sys.exit(main())
