"""Empty-database trial drill. Synthetic rows only. No network model.

The caller DSN is read for host, port, role, and password, then refused when
it already names k12, postgres, or either drill database. The script creates
k12_r11_src and k12_r11_dst, runs the teacher loop, and deletes both databases
and the temp directory on the way out.
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trial_bundle import database_name, redact, split_dsn  # noqa: E402

_SRC = "k12_r11_src"
_DST = "k12_r11_dst"
_DRILL = frozenset({_SRC, _DST})
_FORBIDDEN = frozenset({"k12", "postgres", _SRC, _DST})
_BOOK = "synth-r11-book"
_ADMIN = "synth-trial-admin"
_TEACHER = "synth-r11-teacher"
_EXTERNAL = "synth-r11-ext-01"
_PRESET_USERS = ("admin-synth", "teacher-synth")
_PRESET_STUDENTS = ("student-synth", "student-synth-2")
_ROLE = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DrillFail(Exception):
    def __init__(self, phase: str, code: str) -> None:
        self.phase = phase
        self.code = code


class Secrets:
    def __init__(self) -> None:
        self.values: list[str] = []

    def add(self, value: str) -> str:
        if value:
            self.values.append(value)
        return value

    def clean(self, text: str) -> str:
        return redact(text, self.values)


def minimal_jpeg() -> bytes:
    """Smallest JPEG the intake checker accepts. Standard library only."""
    payload = b"synth-r11"
    length = len(payload) + 2
    segment = bytes((0xFF, 0xE0, (length >> 8) & 0xFF, length & 0xFF)) + payload
    return b"\xff\xd8" + segment + bytes((0xFF, 0xDA, 0x00, 0x02)) + b"synth" + b"\xff\xd9"


def refused_name(name: str) -> bool:
    return name.casefold() in {item.casefold() for item in _FORBIDDEN}


def guard(dsn: str, port: int | None) -> int:
    """Return 2 when the caller DSN or port must not start a drill."""
    if not dsn.strip():
        print("DRILL FAIL: K12_PG_DSN is empty", file=sys.stderr)
        return 2
    try:
        fields = split_dsn(dsn.strip())
    except RuntimeError:
        print("DRILL FAIL: K12_PG_DSN is invalid", file=sys.stderr)
        return 2
    if refused_name(fields["name"]):
        print(f"DRILL FAIL: refusing database {fields['name']}", file=sys.stderr)
        return 2
    if port == 8765:
        print("DRILL FAIL: port 8765 is reserved", file=sys.stderr)
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the empty-database trial pack drill.")
    parser.add_argument("--port", type=int, default=None)
    return parser


def _secret() -> str:
    return "Aa1" + secrets.token_hex(12)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public(exc: BaseException, secrets: Secrets) -> str:
    text = secrets.clean(str(exc))
    if "://" in text or "password" in text.lower() or "[redacted]" in text:
        return type(exc).__name__
    return f"{type(exc).__name__}: {text}"


def _free_port() -> int:
    for _ in range(8):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port != 8765:
            return port
    raise DrillFail("1", "no_free_port")


def _container(port: str) -> str | None:
    completed = subprocess.run(
        ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.ID}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    found = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(found) != 1:
        return None
    return found[0]


def _docker(container: str, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", "exec", "-i", "-u", "postgres", container, *args],
        capture_output=True,
        check=False,
    )


def _psql(container: str, database: str, statement: str) -> None:
    if database not in _DRILL and database != "postgres":
        raise DrillFail("7", "refusing_psql_target")
    completed = _docker(
        container,
        ["psql", "-d", database, "-v", "ON_ERROR_STOP=1", "-q", "-c", statement],
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "psql failed")


def _reset(container: str, name: str, role: str) -> None:
    if name not in _DRILL or _ROLE.fullmatch(role) is None:
        raise DrillFail("1", "refusing_reset")
    _psql(
        container,
        "postgres",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
    )
    _psql(container, "postgres", f"DROP DATABASE IF EXISTS {name}")
    _psql(container, "postgres", f"CREATE DATABASE {name} OWNER {role}")
    _psql(container, name, f"ALTER SCHEMA public OWNER TO {role}")


def _drop(container: str, name: str) -> None:
    if name not in _DRILL:
        raise DrillFail("7", "refusing_drop")
    _psql(
        container,
        "postgres",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
    )
    _psql(container, "postgres", f"DROP DATABASE IF EXISTS {name}")


def _databases(container: str) -> set[str]:
    completed = _docker(
        container,
        ["psql", "-d", "postgres", "-tA", "-c", "SELECT datname FROM pg_database"],
    )
    if completed.returncode != 0:
        raise RuntimeError("database list failed")
    return {line.strip() for line in completed.stdout.decode("utf-8", errors="replace").splitlines() if line.strip()}


def _shipped() -> tuple[str, ...]:
    from backend.bootstrap.migrate import discover

    return tuple(item.version for item in discover(ROOT))


def _query(dsn: str, statement: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return list(conn.execute(statement, params).fetchall())


def _replace_database(dsn: str, name: str) -> str:
    if name not in _DRILL:
        raise DrillFail("1", "refusing_retarget")
    parts = urlsplit(dsn)
    return parts._replace(path="/" + name).geturl()


def _tool_path(shim: Path) -> str:
    env_root = Path(sys.executable).resolve().parent
    parts = [str(shim), str(env_root / "Library" / "bin"), str(env_root / "Scripts"), str(env_root)]
    return os.pathsep.join(parts) + os.pathsep + os.environ.get("PATH", "")


def _write_shims(directory: Path, container: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "pg_client.py"
    script.write_text(_SHIM, encoding="utf-8")
    launch = f'@echo off\r\n"{sys.executable}" "{script}" %1\r\n'
    (directory / "pg_dump.cmd").write_text(launch.replace("%1", "pg_dump"), encoding="utf-8")
    (directory / "psql.cmd").write_text(launch.replace("%1", "psql"), encoding="utf-8")
    (directory / "container.txt").write_text(container, encoding="utf-8")


_SHIM = """\
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ALLOWED = {"k12_r11_src", "k12_r11_dst"}
_ROLE = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    database = os.environ.get("PGDATABASE", "")
    role = os.environ.get("PGUSER", "")
    container = Path(__file__).with_name("container.txt").read_text(encoding="utf-8").strip()
    if database not in _ALLOWED or _ROLE.fullmatch(role) is None or not container:
        sys.stderr.write("refusing database\\n")
        return 2
    if mode == "pg_dump":
        command = [
            "docker", "exec", "-i", "-u", "postgres", container,
            "pg_dump", "-d", database, "--format=plain", "--no-owner", "--no-acl",
        ]
        completed = subprocess.run(command, capture_output=True, check=False)
    elif mode == "psql":
        payload = ("SET ROLE " + role + ";\\n").encode("ascii") + sys.stdin.buffer.read()
        command = [
            "docker", "exec", "-i", "-u", "postgres", container,
            "psql", "-d", database, "-v", "ON_ERROR_STOP=1", "-q",
        ]
        completed = subprocess.run(command, input=payload, capture_output=True, check=False)
    else:
        sys.stderr.write("refusing database\\n")
        return 2
    sys.stdout.buffer.write(completed.stdout)
    sys.stderr.buffer.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _stop(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    for handle in getattr(proc, "_drill_logs", ()):
        handle.close()
    if hasattr(proc, "_drill_logs"):
        proc._drill_logs = ()


class Http:
    def __init__(self, base: str, secrets: Secrets) -> None:
        self.base = base
        self.secrets = secrets
        self.csrf = ""
        self.phase = "http"
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def login(self, username: str, secret: str) -> None:
        status, body = self.request("POST", "/api/login", {"username": username, "secret": secret}, expect=200)
        token = body.get("csrf_token") if isinstance(body, dict) else ""
        if status != 200 or not isinstance(token, str) or not token:
            raise DrillFail(self.phase, "login")
        self.csrf = token

    def request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        *,
        raw: bytes | None = None,
        content_type: str = "application/json",
        expect: int | None = None,
    ) -> tuple[int, object]:
        data: bytes | None
        if raw is not None:
            data = raw
        elif payload is None:
            data = None if method == "GET" else b""
        else:
            data = json.dumps(payload).encode("utf-8")
        headers = {"X-Request-Id": "drill-r11", "Accept": "application/json"}
        if data is not None and method != "GET":
            headers["Content-Type"] = content_type
        if self.csrf and path != "/api/login":
            headers["X-K12-CSRF"] = self.csrf
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = self._opener.open(request, timeout=60)
            status = response.status
            blob = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            blob = exc.read()
        except urllib.error.URLError as exc:
            raise DrillFail("1", "http_" + type(exc.reason).__name__ if getattr(exc, "reason", None) else "http") from None
        if expect is not None and status != expect:
            code = _error_code(blob)
            raise DrillFail(self.phase, f"{status}_{code or 'body'}")
        if content_type == "application/pdf" or path.endswith("/image") or "/files/" in path:
            return status, blob
        if not blob:
            return status, {}
        try:
            return status, json.loads(blob.decode("utf-8"))
        except json.JSONDecodeError:
            return status, blob

    def code_of(self, method: str, path: str, payload: object) -> tuple[int, str]:
        status, body = self.request(method, path, payload)
        if isinstance(body, dict):
            return status, str(body.get("code") or "")
        return status, ""


def _error_code(blob: bytes) -> str:
    try:
        value = json.loads(blob.decode("utf-8")).get("code")
    except (UnicodeError, json.JSONDecodeError, AttributeError):
        return ""
    return str(value or "")


def _book(dry_run: bool) -> dict[str, object]:
    choice = _question("1:1", "1", "single_choice", "choice", [{"type": "text", "value": "synth-r11-choice"}])
    solved = _question("1:2", "2", "solution", "worked", [{"type": "math", "latex": r"\textcircled{1}"}])
    solved["options"] = []
    return {
        "subject_id": "math",
        "dry_run": dry_run,
        "pages": [
            {
                "pdf_page": 1,
                "role": "questions",
                "volume": "questions",
                "questions": _draft([choice, solved]),
                "answers": [],
            },
            {
                "pdf_page": 1,
                "role": "answers",
                "volume": "answers",
                "answers": [
                    _answer("1:1", "synth-r11-a", []),
                    _answer(
                        "1:2",
                        "",
                        [
                            {"sub_key": "1", "role": "result", "order": 1, "content": [{"type": "text", "value": "synth-r11-part"}]},
                            {"sub_key": "1", "role": "step", "order": 2, "content": [{"type": "text", "value": "synth-r11-step"}]},
                        ],
                    ),
                ],
            },
        ],
        "pairing": [{"answer_page": 1, "question_page": 1}],
        "toc": [{"pdf_page": 1, "text": "## 一、synth-ch\nsynth-sec\nsynth-les \u2026 1\n"}],
        "toc_page_offset": 0,
        "answer_space": [{"page": 1, "key": "1:2", "space": "small"}],
    }


def _draft(questions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "contract": "k12-question-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "preface": "",
        "source": {"pdf_page": 1},
        "questions": questions,
    }


def _question(key: str, number: str, kind: str, structure: str, stem: list[dict[str, str]]) -> dict[str, object]:
    return {
        "key": key,
        "section": "一",
        "number": number,
        "type": kind,
        "structure": structure,
        "status": "confirmed",
        "stem": stem,
        "options": [{"key": "A", "content": [{"type": "text", "value": "2"}]}],
        "subquestions": [],
        "assets": [],
        "geometry": None,
    }


def _answer(key: str, text: str, parts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "contract": "k12-answer-draft",
        "contract_version": 1,
        "schema_version": 1,
        "ok": True,
        "reason": "",
        "question_key": key,
        "key": key + ":ocr:1",
        "origin": "ocr",
        "status": "confirmed",
        "applicable": True,
        "source": {"pdf_page": 1},
        "content": [] if parts else [{"type": "text", "value": text}],
        "parts": parts,
        "assets": [],
    }


def _issuable(tree: object) -> int:
    if not isinstance(tree, dict):
        return -1
    total = 0
    chapters = tree.get("chapters")
    if not isinstance(chapters, list):
        return -1
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        sections = chapter.get("sections")
        if not isinstance(sections, list):
            continue
        for section in sections:
            if not isinstance(section, dict):
                continue
            lessons = section.get("lessons")
            if not isinstance(lessons, list):
                continue
            for lesson in lessons:
                if isinstance(lesson, dict):
                    total += int(lesson.get("issuable_count") or 0)
    return total


def _start_server(port: int, dsn: str, file_dir: Path, log_dir: Path, secrets: Secrets, *, bootstrap: tuple[str, str] | None) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    for name in (
        "K12_AI_API_KEY",
        "K12_AI_BASE_URL",
        "K12_AI_MODEL",
        "K12_ERROR_WEBHOOK_URL",
        "K12_BOOTSTRAP_ADMIN_USERNAME",
        "K12_BOOTSTRAP_ADMIN_PASSWORD",
        "K12_BACKUP_PASSPHRASE",
    ):
        env.pop(name, None)
    env.update(
        {
            "K12_ENV": "production",
            "K12_AI_PROVIDER": "mock",
            "K12_SESSION_SECURE": "0",
            "K12_OPENAPI": "0",
            "K12_CORS_ORIGINS": f"http://127.0.0.1:{port}",
            "K12_PG_DSN": dsn,
            "K12_FILE_DIR": str(file_dir),
            "K12_LOG_DIR": str(log_dir),
            "PATH": _tool_path(log_dir.parent / "bin"),
        }
    )
    if bootstrap is not None:
        env["K12_BOOTSTRAP_ADMIN_USERNAME"] = bootstrap[0]
        env["K12_BOOTSTRAP_ADMIN_PASSWORD"] = bootstrap[1]
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = open(log_dir / "uvicorn.out", "ab")
    stderr = open(log_dir / "uvicorn.err", "ab")
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.bootstrap.http_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception:
        stdout.close()
        stderr.close()
        raise
    proc._drill_logs = (stdout, stderr)  # type: ignore[attr-defined]
    return proc


def _wait_ready(proc: subprocess.Popen[bytes], http: Http, secrets: Secrets, phase: str) -> None:
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            raise DrillFail(phase, "server_exited")
        try:
            health, health_body = http.request("GET", "/health")
            ready, _ready_body = http.request("GET", "/health/ready")
        except DrillFail:
            time.sleep(0.3)
            continue
        if health == 200 and isinstance(health_body, dict) and health_body.get("status") == "ok" and ready == 200:
            return
        time.sleep(0.3)
    raise DrillFail(phase, "server_not_ready")


def _run_script(args: list[str], env: dict[str, str], secrets: Secrets) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = secrets.clean((completed.stdout + "\n" + completed.stderr)[-800:])
        if "://" in detail or "password" in detail.lower():
            detail = "script_failed"
        raise RuntimeError(detail or "script_failed")
    leaked = secrets.clean(completed.stdout + completed.stderr)
    if any(secret and secret in (completed.stdout + completed.stderr) for secret in secrets.values):
        raise RuntimeError("script output leaked a secret")
    return completed


def _child_env(base_dsn: str, file_dir: Path, passphrase: str, shim: Path, secrets: Secrets) -> dict[str, str]:
    env = os.environ.copy()
    env["K12_PG_DSN"] = base_dsn
    env["K12_FILE_DIR"] = str(file_dir)
    env["K12_BACKUP_PASSPHRASE"] = passphrase
    env["PATH"] = _tool_path(shim)
    env.pop("K12_BOOTSTRAP_ADMIN_PASSWORD", None)
    env.pop("K12_BOOTSTRAP_ADMIN_USERNAME", None)
    secrets.add(passphrase)
    return env


def _pdf(http: Http, file_id: str) -> bytes:
    status, body = http.request("GET", "/api/practice/files/" + file_id, content_type="application/pdf")
    if status != 200 or not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise DrillFail("3", "pdf")
    return body


def _snapshot(teacher: Http, admin: Http, paper_id: str, follow_id: str, intake_id: str) -> dict[str, object]:
    _status, lessons = teacher.request("GET", f"/api/catalog/books/{_BOOK}/lessons", expect=200)
    original = _pdf(teacher, _file_id(teacher, paper_id))
    follow = _pdf(teacher, _file_id(teacher, follow_id))
    photo_status, photo = teacher.request("GET", f"/api/practice/intake/{intake_id}/image", content_type="image/jpeg")
    if photo_status != 200 or not isinstance(photo, bytes):
        raise DrillFail("5", "photo")
    _status, review = teacher.request("GET", f"/api/practice/papers/{paper_id}/review", expect=200)
    _status, follow_body = teacher.request("GET", "/api/practice/papers", expect=200)
    _status, accuracy = admin.request("GET", "/api/admin/ai/accuracy", expect=200)
    papers = follow_body.get("papers") if isinstance(follow_body, dict) else []
    by_id = {str(row.get("paper_id")): row for row in papers if isinstance(row, dict)}
    return {
        "lessons": lessons,
        "pdf": {_sha256(original): paper_id, _sha256(follow): follow_id},
        "source_paper_id": by_id.get(follow_id, {}).get("source_paper_id"),
        "photo": _sha256(photo),
        "decisions": _decisions(review),
        "accuracy": _accuracy(accuracy),
    }


def _file_id(http: Http, paper_id: str) -> str:
    _status, body = http.request("GET", "/api/practice/papers", expect=200)
    papers = body.get("papers") if isinstance(body, dict) else []
    for row in papers if isinstance(papers, list) else []:
        if isinstance(row, dict) and row.get("paper_id") == paper_id and row.get("file_id"):
            return str(row["file_id"])
    raise DrillFail("5", "file_id")


def _decisions(review: object) -> list[dict[str, object]]:
    if not isinstance(review, dict) or not isinstance(review.get("items"), list):
        raise DrillFail("3", "review")
    rows: list[dict[str, object]] = []
    for item in review["items"]:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        rows.append(
            {
                "order_no": item.get("order_no"),
                "source": decision.get("source"),
                "verdict": decision.get("verdict"),
            }
        )
    return rows


def _accuracy(body: object) -> dict[str, object]:
    if not isinstance(body, dict):
        raise DrillFail("3", "accuracy")
    runs = body.get("runs") if isinstance(body.get("runs"), dict) else {}
    items = body.get("items") if isinstance(body.get("items"), dict) else {}
    source = items.get("by_source") if isinstance(items.get("by_source"), dict) else {}
    return {
        "succeeded": runs.get("succeeded"),
        "total": runs.get("total"),
        "linked_ai": items.get("linked_ai"),
        "decided_total": items.get("decided_total"),
        "adopted": source.get("adopted"),
        "revised": source.get("revised"),
        "agreed": items.get("agreed"),
        "disagreed": items.get("disagreed"),
    }


def _phase_line(number: int) -> None:
    print(f"PHASE {number} ok", flush=True)


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    args = _parser().parse_args(argv)
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    refused = guard(dsn, args.port)
    if refused:
        return refused
    fields = split_dsn(dsn)
    port = args.port if args.port is not None else _free_port()
    if port == 8765:
        print("DRILL FAIL: port 8765 is reserved", file=sys.stderr)
        return 2
    secrets = Secrets()
    secrets.add(fields["password"])
    container: str | None = None
    root: Path | None = None
    server: subprocess.Popen[bytes] | None = None
    code = 1
    try:
        container = _container(fields["port"])
        if container is None:
            print("DRILL FAIL: no single container publishes this port", file=sys.stderr)
            return 1
        role = fields["user"]
        if _ROLE.fullmatch(role) is None:
            print("DRILL FAIL: refusing role", file=sys.stderr)
            return 2
        current = _query(dsn, "SELECT current_database()")
        if not current or str(current[0][0]) != fields["name"] or refused_name(str(current[0][0])):
            print("DRILL FAIL: current_database refused", file=sys.stderr)
            return 2
        root = Path(tempfile.mkdtemp(prefix="k12-r11-"))
        src_files = root / "src_files"
        dst_files = root / "dst_files"
        backups = root / "backups"
        archives = root / "archives"
        logs = root / "logs"
        for path in (src_files, dst_files, backups, archives, logs):
            path.mkdir()
        _write_shims(root / "bin", container)
        _reset(container, _SRC, role)
        _reset(container, _DST, role)
        src_dsn = _replace_database(dsn, _SRC)
        dst_dsn = _replace_database(dsn, _DST)
        bootstrap = secrets.add(_secret())
        admin_next = secrets.add(_secret())
        teacher_secret = secrets.add(_secret())
        server = _start_server(port, src_dsn, src_files, logs, secrets, bootstrap=(_ADMIN, bootstrap))
        http = Http(f"http://127.0.0.1:{port}", secrets)
        http.phase = "1"
        _wait_ready(server, http, secrets, "1")
        versions = [str(row[0]) for row in _query(src_dsn, "SELECT version FROM schema_migrations ORDER BY version")]
        shipped = _shipped()
        if tuple(versions) != shipped or len(shipped) != 20:
            raise DrillFail("1", "migrations")
        preset = _query(
            src_dsn,
            """
            SELECT
              (SELECT count(*) FROM users WHERE username IN (%s, %s)),
              (SELECT count(*) FROM students
                WHERE student_id IN (%s, %s) OR external_id IN (%s, %s)),
              (SELECT count(*) FROM questions WHERE question_id = 'q-v1')
            """,
            (*_PRESET_USERS, *_PRESET_STUDENTS, *_PRESET_STUDENTS),
        )[0]
        if tuple(preset) != (0, 0, 0):
            raise DrillFail("1", "preset_rows")
        _phase_line(1)
        http.phase = "2"
        http.login(_ADMIN, bootstrap)
        blocked, blocked_code = http.code_of(
            "POST",
            "/api/admin/teachers",
            {"username": _TEACHER, "secret": teacher_secret},
        )
        if blocked != 403 or blocked_code != "password_change_required":
            raise DrillFail("2", "password_change_required")
        status, changed = http.request(
            "POST",
            "/api/account/password",
            {"old_secret": bootstrap, "new_secret": admin_next},
            expect=200,
        )
        if status != 200 or not isinstance(changed, dict) or changed.get("ok") is not True:
            raise DrillFail("2", "password_change")
        dry_status, dry = http.request(
            "POST",
            f"/api/admin/catalog/books/{_BOOK}/import",
            _book(True),
            expect=200,
        )
        if dry_status != 200 or not isinstance(dry, dict) or dry.get("written") is not False:
            raise DrillFail("2", "dry_run")
        saved_status, saved = http.request(
            "POST",
            f"/api/admin/catalog/books/{_BOOK}/import",
            _book(False),
            expect=200,
        )
        if saved_status != 200 or not isinstance(saved, dict) or saved.get("written") is not True:
            raise DrillFail("2", "import")
        question_ids = [
            str(row.get("question_version_id"))
            for row in saved.get("questions", [])
            if isinstance(row, dict) and row.get("question_version_id")
        ]
        if len(question_ids) != 2:
            raise DrillFail("2", "questions")
        lesson_status, lessons = http.request("GET", f"/api/catalog/books/{_BOOK}/lessons", expect=200)
        if lesson_status != 200 or _issuable(lessons) != 0:
            raise DrillFail("2", "lessons_before_publish")
        tree = lessons if isinstance(lessons, dict) else {}
        chapters = tree.get("chapters")
        if (
            tree.get("book_id") != _BOOK
            or not isinstance(chapters, list)
            or not chapters
            or chapters[0].get("title") != "一、synth-ch"
        ):
            raise DrillFail("2", "lesson_tree")
        _phase_line(2)
        teacher_status, teacher = http.request(
            "POST",
            "/api/admin/teachers",
            {"username": _TEACHER, "secret": teacher_secret},
            expect=200,
        )
        student_status, student = http.request(
            "POST",
            "/api/admin/students",
            {"external_id": _EXTERNAL, "grade": "7", "subject_id": "math", "name": None},
            expect=200,
        )
        if teacher_status != 200 or student_status != 200 or not isinstance(teacher, dict) or not isinstance(student, dict):
            raise DrillFail("3", "accounts")
        http.request(
            "POST",
            "/api/admin/grants",
            {
                "teacher_id": teacher["user_id"],
                "student_id": student["student_id"],
                "subject_id": "math",
            },
            expect=200,
        )
        teacher_http = Http(http.base, secrets)
        teacher_http.phase = "3"
        teacher_http.login(_TEACHER, teacher_secret)
        for question_id in question_ids:
            teacher_http.request("POST", f"/api/catalog/{question_id}/publish", {}, expect=200)
        _ready_status, ready_lessons = teacher_http.request("GET", f"/api/catalog/books/{_BOOK}/lessons", expect=200)
        if _issuable(ready_lessons) != 2:
            raise DrillFail("3", "issuable_count")
        issued_status, issued = teacher_http.request(
            "POST",
            "/api/practice/papers",
            {
                "student_id": student["student_id"],
                "subject_id": "math",
                "review_version_id": "rev-synth-r11",
                "items": [{"question_version_id": question_id} for question_id in question_ids],
            },
            expect=200,
        )
        if issued_status != 200 or not isinstance(issued, dict) or int(issued.get("page_count") or 0) != 1:
            raise DrillFail("3", "issue")
        paper_id = str(issued["paper_id"])
        original_pdf = _pdf(teacher_http, str(issued["file_id"]))
        handed, hand_body = teacher_http.request("POST", f"/api/practice/papers/{paper_id}/handout", {})
        if handed != 200 or not isinstance(hand_body, dict) or hand_body.get("status") != "已发放":
            raise DrillFail("3", "handout")
        uploaded, upload = teacher_http.request(
            "PUT",
            f"/api/practice/papers/{paper_id}/pages/1/intake?located_by=manual",
            raw=minimal_jpeg(),
            content_type="image/jpeg",
            expect=200,
        )
        if uploaded != 200 or not isinstance(upload, dict) or not str(upload.get("intake_id") or "").startswith("intake-"):
            raise DrillFail("3", "intake")
        intake_id = str(upload["intake_id"])
        started_run, run_body = teacher_http.request("POST", f"/api/practice/intake/{intake_id}/ai-runs", {})
        if started_run != 202 or not isinstance(run_body, dict):
            raise DrillFail("3", "ai_run")
        run_id = str(run_body.get("run_id") or "")
        deadline = time.time() + 20
        report: object = {}
        while time.time() < deadline:
            _status, report = teacher_http.request("GET", f"/api/practice/ai-runs/{run_id}")
            if isinstance(report, dict) and report.get("status") in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
        if not isinstance(report, dict) or report.get("status") != "succeeded":
            raise DrillFail("3", "ai_status")
        _status, review = teacher_http.request("GET", f"/api/practice/papers/{paper_id}/review", expect=200)
        items = review.get("items") if isinstance(review, dict) else None
        if not isinstance(items, list) or len(items) < 2:
            raise DrillFail("3", "review_items")
        ready = [
            int(item["order_no"])
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("suggestion"), dict)
            and item["suggestion"].get("verdict") not in {None, "unsure"}
        ]
        if len(ready) < 2:
            raise DrillFail("3", "suggestions")
        adopted, adopt_body = teacher_http.request(
            "PUT",
            f"/api/practice/papers/{paper_id}/items/{ready[0]}/decision",
            {"action": "adopt"},
        )
        revised, revise_body = teacher_http.request(
            "PUT",
            f"/api/practice/papers/{paper_id}/items/{ready[1]}/decision",
            {"action": "revise", "verdict": "incorrect"},
        )
        if not isinstance(adopt_body, dict) or adopt_body.get("source") != "adopted":
            raise DrillFail("3", "adopt")
        if not isinstance(revise_body, dict) or revise_body.get("source") != "revised" or revise_body.get("verdict") != "incorrect":
            raise DrillFail("3", "revise")
        if adopted != 200 or revised != 200:
            raise DrillFail("3", "decision_status")
        accuracy_status, accuracy = http.request("GET", "/api/admin/ai/accuracy", expect=200)
        counted = _accuracy(accuracy)
        if accuracy_status != 200 or int(counted["succeeded"] or 0) < 1 or int(counted["linked_ai"] or 0) < 1:
            raise DrillFail("3", "accuracy")
        followed, follow_body = teacher_http.request("POST", f"/api/practice/papers/{paper_id}/follow-up", {})
        if followed != 200 or not isinstance(follow_body, dict) or follow_body.get("source_paper_id") != paper_id:
            raise DrillFail("3", "follow_up")
        follow_id = str(follow_body["paper_id"])
        follow_pdf = _pdf(teacher_http, str(follow_body["file_id"]))
        if follow_id == paper_id or not follow_pdf:
            raise DrillFail("3", "follow_pdf")
        before = _snapshot(teacher_http, http, paper_id, follow_id, intake_id)
        _phase_line(3)
        _stop(server)
        server = None
        phrase = secrets.add(_secret())
        backup_env = _child_env(src_dsn, src_files, phrase, root / "bin", secrets)
        backup = _run_script(
            [str(ROOT / "scripts" / "backup_trial.py"), "--out-dir", str(backups)],
            backup_env,
            secrets,
        )
        archives_found = list(backups.glob("*.tar.gz.enc"))
        plain = list(backups.glob("*.tar.gz"))
        if len(archives_found) != 1 or plain or "BACKUP PASS" not in backup.stdout:
            raise DrillFail("4", "backup")
        verified = _run_script(
            [str(ROOT / "scripts" / "restore_trial.py"), str(archives_found[0]), "--verify-only"],
            backup_env,
            secrets,
        )
        if verified.returncode != 0 or "VERIFIED" not in verified.stdout:
            raise DrillFail("4", "verify")
        _phase_line(4)
        restore_env = _child_env(dst_dsn, dst_files, phrase, root / "bin", secrets)
        restored = _run_script(
            [str(ROOT / "scripts" / "restore_trial.py"), str(archives_found[0])],
            restore_env,
            secrets,
        )
        if "RESTORED" not in restored.stdout:
            raise DrillFail("5", "restore")
        server = _start_server(port, dst_dsn, dst_files, logs / "dst", secrets, bootstrap=None)
        again = Http(f"http://127.0.0.1:{port}", secrets)
        again.phase = "5"
        _wait_ready(server, again, secrets, "5")
        again.login(_ADMIN, admin_next)
        teacher_again = Http(again.base, secrets)
        teacher_again.phase = "5"
        teacher_again.login(_TEACHER, teacher_secret)
        after = _snapshot(teacher_again, again, paper_id, follow_id, intake_id)
        if after != before:
            raise DrillFail("5", "restored_match")
        _phase_line(5)
        again.phase = "6"
        teacher_again.phase = "6"
        aged = _query(
            dst_dsn,
            """
            UPDATE teacher_decision
            SET decided_at = now() - interval '35 days'
            WHERE paper_id = %s AND voided_at IS NULL
            RETURNING decision_id
            """,
            (paper_id,),
        )
        if len(aged) < 2:
            raise DrillFail("6", "age")
        dry_archive = _run_script(
            [str(ROOT / "scripts" / "archive_intake.py"), "--dry-run", "--out-dir", str(archives)],
            restore_env,
            secrets,
        )
        if "confirmed=1" not in dry_archive.stdout:
            raise DrillFail("6", "archive_dry_run")
        packed = _run_script(
            [str(ROOT / "scripts" / "archive_intake.py"), "--out-dir", str(archives)],
            restore_env,
            secrets,
        )
        if "archived=1" not in packed.stdout:
            raise DrillFail("6", "archive")
        sealed = list(archives.glob("*.tar.gz.enc"))
        if len(sealed) != 1 or list(archives.glob("*.tar.gz")):
            raise DrillFail("6", "archive_file")
        checked = _run_script(
            [str(ROOT / "scripts" / "archive_intake.py"), "--verify-archive", str(sealed[0])],
            restore_env,
            secrets,
        )
        if "ARCHIVE VERIFIED" not in checked.stdout:
            raise DrillFail("6", "archive_verify")
        photo_status, photo_body = teacher_again.request(
            "GET",
            f"/api/practice/intake/{intake_id}/image",
            content_type="image/jpeg",
        )
        photo_code = _error_code(photo_body if isinstance(photo_body, bytes) else b"")
        if photo_status != 410 or photo_code != "intake_archived":
            raise DrillFail("6", "archived_photo")
        if not _pdf(teacher_again, _file_id(teacher_again, paper_id)) or not _pdf(
            teacher_again, _file_id(teacher_again, follow_id)
        ):
            raise DrillFail("6", "pdf_after_archive")
        teacher_again.request("GET", f"/api/practice/papers/{paper_id}/review", expect=200)
        grade_status, _grade = teacher_again.request("GET", f"/papers/{paper_id}/grade", content_type="text/html")
        if grade_status != 200:
            raise DrillFail("6", "grade_page")
        again.request("GET", "/api/admin/ai/accuracy", expect=200)
        _phase_line(6)
        code = 0
    except DrillFail as exc:
        print(f"DRILL FAIL: phase={exc.phase} code={exc.code}", file=sys.stderr)
        code = 1
    except Exception as exc:
        print(f"DRILL FAIL: {_public(exc, secrets)}", file=sys.stderr)
        code = 1
    finally:
        _stop(server)
        server = None
        if container is not None:
            try:
                _drop(container, _SRC)
                _drop(container, _DST)
                left = _databases(container) & _DRILL
                if left:
                    print("DRILL CLEANUP: temporary database remains", file=sys.stderr)
                    code = 1
            except Exception as exc:
                print(f"DRILL CLEANUP: {_public(exc, secrets)}", file=sys.stderr)
                code = 1
        if root is not None:
            for _attempt in range(5):
                shutil.rmtree(root, ignore_errors=True)
                if not root.exists():
                    break
                time.sleep(0.4)
            if root.exists():
                print("DRILL CLEANUP: temporary directory remains", file=sys.stderr)
                code = 1
    if code == 0:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        print(
            "TRIAL PACK DRILL PASS "
            f"migrations=20 books=1 papers=2 backup_verified=yes restored_match=yes "
            f"archived=1 elapsed_ms={elapsed_ms}"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
