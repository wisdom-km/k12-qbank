"""Joint restore drill for one scratch database and two fixture files.

The caller's database is only read to learn its name. `k12` and `postgres`
are refused. Fixture rows are written in `k12_m11_src`, dumped with the two
files as one restore point, and restored into the empty database
`k12_m11_dst` plus a new directory. This script does not migrate down and
does not write publication ports.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_LIVE = frozenset({"k12", "postgres"})
_SRC = "k12_m11_src"
_DST = "k12_m11_dst"
_DRILL = frozenset({_SRC, _DST})
_ROLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PAPER = "paper-m11"
_PAGE = "file-m11-page"
_NOTE = "file-m11-note"
_CONFIRM = "confirmation-m11"


def database_name(dsn: str) -> str:
    path = urlsplit(dsn).path.lstrip("/")
    return path.split("/")[0]


def refused(name: str) -> bool:
    return name in _LIVE or name in _DRILL


def replace_database(dsn: str, name: str) -> str:
    if name not in _DRILL:
        raise RuntimeError("refusing to retarget")
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))


def _role(dsn: str) -> str:
    role = urlsplit(dsn).username or ""
    if _ROLE.fullmatch(role) is None:
        raise RuntimeError("refusing role")
    return role


def _port(dsn: str) -> str:
    port = urlsplit(dsn).port
    return str(port or 5432)


def _public(exc: BaseException) -> str:
    text = str(exc)
    if "://" in text or "password" in text.lower():
        return type(exc).__name__
    return f"{type(exc).__name__}: {text}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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


def _docker(container: str, args: list[str], payload: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", "exec", "-i", "-u", "postgres", container, *args],
        input=payload,
        capture_output=True,
        check=False,
    )


def _psql(container: str, database: str, statement: str) -> None:
    if database not in _DRILL and database != "postgres":
        raise RuntimeError("refusing psql target")
    completed = _docker(
        container,
        ["psql", "-d", database, "-v", "ON_ERROR_STOP=1", "-q", "-c", statement],
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "psql failed")


def _reset(container: str, name: str, role: str) -> None:
    if name not in _DRILL or _ROLE.fullmatch(role) is None:
        raise RuntimeError("refusing to reset")
    _psql(
        container,
        "postgres",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
    )
    _psql(container, "postgres", f"DROP DATABASE IF EXISTS {name}")
    _psql(container, "postgres", f"CREATE DATABASE {name} OWNER {role}")


def _dump(container: str, name: str) -> bytes:
    if name not in _DRILL:
        raise RuntimeError("refusing to dump")
    completed = _docker(container, ["pg_dump", "-d", name, "--no-owner", "--no-acl"])
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "pg_dump failed")
    return completed.stdout


def _restore(container: str, name: str, role: str, dump: bytes) -> None:
    if name not in _DRILL or _ROLE.fullmatch(role) is None:
        raise RuntimeError("refusing to restore")
    payload = f"SET ROLE {role};\n".encode("ascii") + dump
    completed = _docker(
        container,
        ["psql", "-d", name, "-v", "ON_ERROR_STOP=1", "-q"],
        payload,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "restore failed")


def _seed(dsn: str, page: Path, note: Path) -> tuple[str, str]:
    import psycopg

    page_digest = _sha256(page)
    note_digest = _sha256(note)
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO papers (
                    paper_id, teacher_id, student_id, subject_id,
                    question_version_id, answer_version_id, asset_ids,
                    layout_template_id, review_version_id, file_id, status,
                    item_order, file_checksum, formula
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    _PAPER,
                    "teacher-m11",
                    "student-m11",
                    "math",
                    "qv-m11",
                    "av-m11",
                    [],
                    "sheet-m11",
                    "rv-m11",
                    _PAGE,
                    "issued",
                    [],
                    page_digest,
                    "1+1",
                ),
            )
            conn.execute(
                """
                INSERT INTO paper_pages (
                    paper_id, page_number, page_count, question_version_id,
                    answer_version_id, formula, student_id, item_order,
                    asset_ids, layout_template_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (_PAPER, 1, 1, "qv-m11", "av-m11", "1+1", "student-m11", [], [], "sheet-m11"),
            )
            conn.execute(
                """
                INSERT INTO confirmations (
                    confirmation_id, operation_key, paper_id, sub_question_id,
                    teacher_id, review_version_id, decision, fixture_answer_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (_CONFIRM, "confirm", _PAPER, "sq-m11", "teacher-m11", "rv-m11", "accept", "fix-m11"),
            )
            conn.execute(
                "INSERT INTO files (file_id, purpose, checksum) VALUES (%s, %s, %s)",
                (_PAGE, "page", page_digest),
            )
            conn.execute(
                "INSERT INTO files (file_id, purpose, checksum) VALUES (%s, %s, %s)",
                (_NOTE, "note", note_digest),
            )
    return page_digest, note_digest


def _snapshot(dsn: str) -> dict[str, tuple[tuple[object, ...], ...]]:
    import psycopg

    statements = {
        "versions": "SELECT version FROM schema_migrations ORDER BY version",
        "papers": (
            "SELECT paper_id, student_id, file_id, file_checksum, formula "
            "FROM papers ORDER BY paper_id"
        ),
        "pages": (
            "SELECT paper_id, page_number, student_id FROM paper_pages "
            "ORDER BY paper_id, page_number"
        ),
        "confirmations": (
            "SELECT confirmation_id, paper_id, decision FROM confirmations "
            "ORDER BY confirmation_id"
        ),
        "files": "SELECT file_id, purpose, checksum FROM files ORDER BY file_id",
    }
    found: dict[str, tuple[tuple[object, ...], ...]] = {}
    with psycopg.connect(dsn) as conn:
        for key, statement in statements.items():
            rows = conn.execute(statement).fetchall()
            found[key] = tuple(tuple(row) for row in rows)
    return found


def _drop(container: str, name: str) -> None:
    if name not in _DRILL:
        raise RuntimeError("refusing to drop")
    _psql(
        container,
        "postgres",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
    )
    _psql(container, "postgres", f"DROP DATABASE IF EXISTS {name}")


def main() -> int:
    started = time.perf_counter()
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        print("DRILL FAIL: K12_PG_DSN is empty")
        return 2
    name = database_name(dsn)
    if refused(name):
        print(f"DRILL FAIL: refusing database {name}")
        return 2
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            current = conn.execute("SELECT current_database()").fetchone()
        if current is None or current[0] != name or refused(str(current[0])):
            print("DRILL FAIL: current_database refused")
            return 2
        role = _role(dsn)
        container = _container(_port(dsn))
        if container is None:
            print("DRILL FAIL: no single container publishes this port")
            return 1
    except Exception as exc:
        print(f"DRILL FAIL: {_public(exc)}")
        return 1

    root = Path(tempfile.mkdtemp(prefix="qbank-joint-"))
    try:
        _reset(container, _SRC, role)
        _reset(container, _DST, role)
        from backend.bootstrap.migrate import discover, migrate

        applied = migrate(replace_database(dsn, _SRC), ROOT, "up")
        shipped = tuple(item.version for item in discover(ROOT))
        if tuple(applied) != shipped:
            print("DRILL FAIL: source migrations are not the shipped set")
            return 1
        point = root / "restore-point"
        files = point / "files"
        files.mkdir(parents=True)
        page = files / "page.bin"
        note = files / "note.txt"
        page.write_bytes(b"m11-page-fixture")
        note.write_text("m11-note-fixture", encoding="utf-8")
        page_digest, note_digest = _seed(replace_database(dsn, _SRC), page, note)
        dump = _dump(container, _SRC)
        (point / "db.sql").write_bytes(dump)
        manifest = point / "SHA256SUMS"
        manifest.write_text(
            f"{page_digest}  page.bin\n{note_digest}  note.txt\n",
            encoding="utf-8",
        )
        before = _snapshot(replace_database(dsn, _SRC))
        _restore(container, _DST, role, dump)
        after = _snapshot(replace_database(dsn, _DST))
        if before != after:
            print("DRILL FAIL: restored rows differ")
            return 1
        restored = root / "restored-files"
        restored.mkdir()
        for item in files.iterdir():
            shutil.copy2(item, restored / item.name)
        if _sha256(restored / "page.bin") != page_digest or _sha256(restored / "note.txt") != note_digest:
            print("DRILL FAIL: restored file checksum")
            return 1
        versions = " ".join(str(row[0]) for row in before["versions"])
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        print(
            "DRILL PASS: "
            f"papers={len(before['papers'])} pages={len(before['pages'])} "
            f"confirmations={len(before['confirmations'])} file_rows={len(before['files'])} "
            f"files=2 database={_DST} elapsed_ms={elapsed_ms} migrations={versions}"
        )
        return 0
    except Exception as exc:
        print(f"DRILL FAIL: {_public(exc)}")
        return 1
    finally:
        try:
            _drop(container, _SRC)
            _drop(container, _DST)
        except Exception as exc:
            print(f"DRILL CLEANUP: {_public(exc)}")
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
