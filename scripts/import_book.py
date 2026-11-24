"""Read a book directory, sign in, and call the whole-book import route.

This file does not decide whether a page or a question is accepted.
The server owns those rules. The password, the session cookie, and the CSRF
token stay in memory and are not written to the report.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import quote

_BOOK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
_PAGE_NO = re.compile(r"page_(\d+)", re.IGNORECASE)
_KNOWN_MANIFEST = {"book_id", "subject_id", "pairs"}
_DEFAULT_SERVER = "http://127.0.0.1:8765"


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        print(_python_help(), file=sys.stderr)
        return 1
    args = _parser().parse_args(argv)
    book_dir = args.book_dir
    if not book_dir:
        book_dir = _pick_dir()
        if not book_dir:
            print("没有选择书目录")
            return 1
    try:
        book_id, body = build_request(book_dir)
    except (OSError, json.JSONDecodeError, ValueError):
        print("import-book.json 无法读取，没有发送请求。")
        return 1
    if not book_id:
        print("书清单缺少 book_id，没有发送请求。")
        return 1
    server = args.server or os.environ.get("K12_IMPORT_SERVER", _DEFAULT_SERVER)
    client = _Client(server)
    if not _sign_in(client):
        return 1
    status, dry = client.post(_path(book_id), _with_dry_run(body, True))
    if status != 200 or not isinstance(dry, dict):
        _print_http(status, dry)
        _write_report(book_dir, book_id, _error_report(book_id, status, dry))
        return 1
    _print_totals(dry)
    if _failed(dry) or args.dry_run_only:
        path = _write_report(book_dir, book_id, dry)
        print("report=" + path)
        return 1 if _failed(dry) else 0
    if not _confirm():
        path = _write_report(book_dir, book_id, dry)
        print("已取消。")
        print("report=" + path)
        return 0
    status, written = client.post(_path(book_id), _with_dry_run(body, False))
    if status != 200 or not isinstance(written, dict):
        _print_http(status, written)
        path = _write_report(book_dir, book_id, _error_report(book_id, status, written))
        print("report=" + path)
        return 1
    _print_totals(written)
    path = _write_report(book_dir, book_id, written)
    print("report=" + path)
    return 1 if _failed(written) else 0


def build_request(book_dir: str) -> tuple[str, dict[str, object]]:
    """Return the book id and the JSON body. Outcomes are left to the server."""
    root = Path(book_dir)
    manifest = json.loads((root / "import-book.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest")
    book_id = manifest.get("book_id", "")
    if not isinstance(book_id, str):
        book_id = ""
    return book_id, build_body(manifest, read_pages(root), dry_run=False)


def build_body(manifest: dict[str, object], pages: list[dict[str, object]], *, dry_run: bool) -> dict[str, object]:
    body: dict[str, object] = {
        "subject_id": manifest.get("subject_id", ""),
        "dry_run": dry_run,
        "pages": pages,
        "pairing": manifest.get("pairs", []),
    }
    for key, value in manifest.items():
        if key not in _KNOWN_MANIFEST:
            body[key] = value
    return body


def read_pages(root: Path) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _ignored(relative):
            continue
        stem = _stem(relative)
        if stem is None:
            continue
        slot = grouped.setdefault(stem, {})
        name = relative.name
        if name.endswith(".page-role.txt"):
            slot["role_text"] = path.read_text(encoding="utf-8")
        elif name.endswith(".questions.json"):
            slot["questions_path"] = path
        elif relative.parent.name.endswith(".answers") and name.endswith(".json"):
            slot.setdefault("answer_paths", []).append(path)
    pages: list[dict[str, object]] = []
    for stem, slot in grouped.items():
        role = _role(slot.get("role_text"))
        number = _page_number(stem)
        if number is None:
            continue
        if role == "questions":
            question_path = slot.get("questions_path")
            if not isinstance(question_path, Path):
                continue
            payload = json.loads(question_path.read_text(encoding="utf-8"))
            pages.append(
                {
                    "pdf_page": number,
                    "role": "questions",
                    "questions": payload,
                    "answers": [],
                }
            )
            continue
        answer_paths = slot.get("answer_paths")
        if not isinstance(answer_paths, list) or not answer_paths:
            continue
        answers = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(answer_paths, key=lambda item: item.name)
        ]
        pages.append(
            {
                "pdf_page": number,
                "role": "answers",
                "questions": None,
                "answers": answers,
            }
        )
    pages.sort(key=lambda item: (int(item["pdf_page"]), str(item["role"])))  # type: ignore[arg-type]
    return pages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import one reviewed book directory.")
    parser.add_argument("--book-dir", default="")
    parser.add_argument("--server", default="")
    parser.add_argument("--dry-run-only", action="store_true")
    return parser


def _python_help() -> str:
    return (
        "需要 Python 3.12 或更新。当前是 "
        + sys.version.split()[0]
        + "。请改用 conda 环境 k12-qbank，或设置 K12_PYTHON 指向该环境的 python.exe。"
        + " 见 https://github.com/wisdom-km/k12-qbank/issues/88"
    )


def _pick_dir() -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    chosen = filedialog.askdirectory()
    root.destroy()
    return chosen or ""


def _ignored(relative: Path) -> bool:
    for part in relative.parts:
        if part.startswith(".") or part == "_review_backups":
            return True
    name = relative.name
    return ".reviewed." in name or name.endswith(".reviewed")


def _stem(relative: Path) -> str | None:
    posix = relative.as_posix()
    if _page_number(posix) is None:
        return None
    name = relative.name
    if name.endswith(".questions.json"):
        return relative.with_name(name[: -len(".questions.json")]).as_posix()
    if name.endswith(".page-role.txt"):
        return relative.with_name(name[: -len(".page-role.txt")]).as_posix()
    parent = relative.parent
    if parent.name.endswith(".answers"):
        stem_name = parent.name[: -len(".answers")]
        return parent.with_name(stem_name).as_posix()
    return None


def _page_number(value: str) -> int | None:
    found = _PAGE_NO.findall(value)
    if not found:
        return None
    return int(found[-1])


def _role(raw: object) -> str:
    if not isinstance(raw, str):
        return "questions"
    return "answers" if raw.strip() == "answers" else "questions"


def _with_dry_run(body: dict[str, object], dry_run: bool) -> dict[str, object]:
    copied = dict(body)
    copied["dry_run"] = dry_run
    return copied


def _path(book_id: str) -> str:
    return "/api/admin/catalog/books/" + quote(book_id, safe="") + "/import"


def _sign_in(client: _Client) -> bool:
    username = os.environ.get("K12_IMPORT_USER", "").strip()
    if not username:
        username = input("用户名: ").strip()
    secret = _secret("口令: ")
    status, payload = client.post("/api/login", {"username": username, "secret": secret}, csrf=False)
    token = payload.get("csrf_token") if isinstance(payload, dict) else None
    if status != 200 or not isinstance(token, str) or not token:
        print("登录失败。请检查用户名、口令和服务器是否已启动。")
        return False
    client.csrf = token
    catalog_status, catalog = client.get("/api/catalog")
    if catalog_status == 403 and isinstance(catalog, dict) and catalog.get("code") == "password_change_required":
        return _change_password(client, secret)
    if catalog_status != 200:
        print("登录失败。请检查用户名、口令和服务器是否已启动。")
        return False
    return True


def _change_password(client: _Client, old_secret: str) -> bool:
    print("这个账号要先修改口令。")
    first = _secret("新口令: ")
    second = _secret("再输入一次新口令: ")
    if first != second:
        print("两次新口令不一致。")
        return False
    status, payload = client.post(
        "/api/account/password",
        {"old_secret": old_secret, "new_secret": first},
    )
    if status != 200:
        code = payload.get("code") if isinstance(payload, dict) else ""
        print("修改口令失败。")
        if code:
            print(str(code))
        return False
    return True


def _secret(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\n")


def _confirm() -> bool:
    if sys.stdin.isatty():
        answer = input("确认写入？(y/N) ")
    else:
        answer = sys.stdin.readline()
    return answer.strip().lower() == "y"


def _failed(report: dict[str, object]) -> bool:
    if report.get("reason"):
        return True
    if report.get("conflict"):
        return True
    pages = report.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict) and (page.get("outcome") == "rejected" or page.get("reason")):
                return True
    questions = report.get("questions")
    if isinstance(questions, list):
        for row in questions:
            if isinstance(row, dict) and row.get("outcome") == "conflict":
                return True
    return False


def _print_totals(report: dict[str, object]) -> None:
    print(
        "staged={staged} kept={kept} skipped={skipped} conflict={conflict} written={written} reason={reason}".format(
            staged=report.get("staged"),
            kept=report.get("kept"),
            skipped=report.get("skipped"),
            conflict=report.get("conflict"),
            written=report.get("written"),
            reason=report.get("reason") or "",
        )
    )


def _print_http(status: int, payload: object) -> None:
    code = payload.get("code") if isinstance(payload, dict) else ""
    print("请求失败。状态 " + str(status) + (" " + str(code) if code else ""))


def _error_report(book_id: str, status: int, payload: object) -> dict[str, object]:
    code = ""
    if isinstance(payload, dict) and isinstance(payload.get("code"), str):
        code = str(payload["code"])
    return {
        "book_id": book_id if _BOOK_ID.fullmatch(book_id) else "",
        "dry_run": True,
        "written": False,
        "reason": code or ("http_" + str(status)),
        "pages": [],
        "questions": [],
        "staged": 0,
        "kept": 0,
        "skipped": 0,
        "conflict": 0,
    }


def _public_report(payload: dict[str, object]) -> dict[str, object]:
    pages = []
    raw_pages = payload.get("pages")
    if isinstance(raw_pages, list):
        for page in raw_pages:
            if not isinstance(page, dict):
                continue
            pages.append(
                {
                    "pdf_page": page.get("pdf_page"),
                    "role": page.get("role"),
                    "outcome": page.get("outcome"),
                    "reason": page.get("reason"),
                }
            )
    questions = []
    raw_questions = payload.get("questions")
    if isinstance(raw_questions, list):
        for row in raw_questions:
            if not isinstance(row, dict):
                continue
            questions.append(
                {
                    "original_key": row.get("original_key"),
                    "key": row.get("key"),
                    "question_version_id": row.get("question_version_id"),
                    "outcome": row.get("outcome"),
                    "reason": row.get("reason"),
                }
            )
    book_id = payload.get("book_id")
    safe = book_id if isinstance(book_id, str) and _BOOK_ID.fullmatch(book_id) else ""
    return {
        "book_id": safe,
        "dry_run": payload.get("dry_run"),
        "written": payload.get("written"),
        "reason": payload.get("reason") or "",
        "pages": pages,
        "questions": questions,
        "staged": payload.get("staged"),
        "kept": payload.get("kept"),
        "skipped": payload.get("skipped"),
        "conflict": payload.get("conflict"),
    }


def _write_report(book_dir: str, book_id: str, payload: dict[str, object]) -> str:
    public = _public_report(payload)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3]
    stem = book_id if _BOOK_ID.fullmatch(book_id) else "invalid"
    folder = Path(book_dir) / "_import_reports"
    folder.mkdir(exist_ok=True)
    base = folder / ("import-" + stem + "-" + stamp)
    text = _report_text(public)
    base.with_suffix(".json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    base.with_suffix(".txt").write_text(text, encoding="utf-8")
    return str(base.with_suffix(".json"))


def _report_text(report: dict[str, object]) -> str:
    lines = [
        "book_id=" + str(report.get("book_id") or ""),
        "dry_run=" + str(report.get("dry_run")),
        "written=" + str(report.get("written")),
        "reason=" + str(report.get("reason") or ""),
        "staged={staged} kept={kept} skipped={skipped} conflict={conflict}".format(
            staged=report.get("staged"),
            kept=report.get("kept"),
            skipped=report.get("skipped"),
            conflict=report.get("conflict"),
        ),
    ]
    pages = report.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict):
                lines.append(
                    "page {pdf_page} {role} {outcome} {reason}".format(
                        pdf_page=page.get("pdf_page"),
                        role=page.get("role"),
                        outcome=page.get("outcome"),
                        reason=page.get("reason") or "",
                    )
                )
    questions = report.get("questions")
    if isinstance(questions, list):
        for row in questions:
            if isinstance(row, dict):
                lines.append(
                    "question {original_key} {key} {question_version_id} {outcome} {reason}".format(
                        original_key=row.get("original_key"),
                        key=row.get("key"),
                        question_version_id=row.get("question_version_id"),
                        outcome=row.get("outcome"),
                        reason=row.get("reason") or "",
                    )
                )
    return "\n".join(lines) + "\n"


class _Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.csrf = ""
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def get(self, path: str) -> tuple[int, object]:
        return self._send("GET", path, None, csrf=False)

    def post(self, path: str, body: dict[str, object], *, csrf: bool = True) -> tuple[int, object]:
        return self._send("POST", path, body, csrf=csrf)

    def _send(self, method: str, path: str, body: dict[str, object] | None, *, csrf: bool) -> tuple[int, object]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if csrf and self.csrf:
            headers["X-K12-CSRF"] = self.csrf
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = self._opener.open(request, timeout=30)
            raw = response.read()
            status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        text = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {}
        return status, payload


if __name__ == "__main__":
    sys.exit(main())
