"""One business smoke against a running synthetic server. Not a unit test."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    port = os.environ.get("K12_PORT", "8765")
    base = "http://127.0.0.1:" + port
    health = _json(_open(base + "/health"))
    if health.get("status") != "ok" or set(health) != {"status"}:
        print("SMOKE HTTP FAIL: health " + json.dumps(health, ensure_ascii=False))
        return 1
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
    if b"\\(-3\\)+5" not in pdf or b"student-synth" not in pdf or b"page 1" not in pdf:
        print("SMOKE HTTP FAIL: pdf missing formula, student number, or page")
        return 1
    if b"name-rule omit" not in pdf:
        print("SMOKE HTTP FAIL: pdf missing the no-name rule")
        return 1
    print("SMOKE HTTP PASS")
    return 0


def _open(url: str, body: dict[str, object] | None = None, expect: int = 200) -> urllib.response.addinfourl:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-Request-Id": "smoke-http"},
        method="POST" if body is not None else "GET",
    )
    try:
        response = urllib.request.urlopen(request, timeout=3)
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


if __name__ == "__main__":
    sys.exit(main())
