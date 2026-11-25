"""Joint trial backup: database dump, K12_FILE_DIR bytes, and a SHA-256 manifest.

Encryption is on unless --no-encrypt is passed. The passphrase comes from
K12_BACKUP_PASSPHRASE or an interactive prompt. It is not written to argv or logs.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trial_bundle import (  # noqa: E402
    database_name,
    is_dev_database,
    openssl_convert,
    pg_env,
    redact,
    run,
    sha256_file,
    split_dsn,
    which,
)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _require_phrase(encrypt: bool) -> str:
    if not encrypt:
        return ""
    phrase = os.environ.get("K12_BACKUP_PASSPHRASE", "")
    if not phrase and sys.stdin.isatty() and sys.stdout.isatty():
        phrase = getpass.getpass("K12_BACKUP_PASSPHRASE: ")
    if not phrase:
        print("K12_BACKUP_PASSPHRASE is required", file=sys.stderr)
        raise SystemExit(2)
    return phrase


def _dump_sql(work: Path, args: argparse.Namespace) -> Path:
    dest = work / "db.sql"
    if args.compose_file:
        name = os.environ.get("K12_PG_DATABASE", "").strip() or "k12_trial"
        if is_dev_database(name):
            print("BACKUP REFUSED: database k12", file=sys.stderr)
            raise SystemExit(2)
        program = which("docker")
        completed = run(
            [
                program,
                "compose",
                "-f",
                args.compose_file,
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "k12",
                "-d",
                name,
                "--format=plain",
            ],
            os.environ.copy(),
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            print(redact(detail, [os.environ.get("K12_BACKUP_PASSPHRASE", "")]) or "pg_dump_failed", file=sys.stderr)
            raise SystemExit(1)
        dest.write_bytes(completed.stdout)
        return dest
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        print("K12_PG_DSN is required", file=sys.stderr)
        raise SystemExit(2)
    try:
        fields = split_dsn(dsn)
    except RuntimeError:
        print("K12_PG_DSN is invalid", file=sys.stderr)
        raise SystemExit(2) from None
    if is_dev_database(fields["name"]):
        print("BACKUP REFUSED: database k12", file=sys.stderr)
        raise SystemExit(2)
    program = which("pg_dump")
    completed = run([program, "--format=plain"], pg_env(os.environ.copy(), fields))
    if completed.returncode != 0:
        print("pg_dump_failed", file=sys.stderr)
        raise SystemExit(1)
    dest.write_bytes(completed.stdout)
    return dest


def _list_files(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        relative = path.relative_to(root).as_posix()
        if ".." in Path(relative).parts:
            continue
        rows.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def _snapshot(source: Path, dest: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not source.exists():
        return rows
    for path in sorted(item for item in source.rglob("*") if item.is_file() and not item.is_symlink()):
        relative = path.relative_to(source).as_posix()
        if ".." in Path(relative).parts:
            continue
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        rows.append({"path": relative, "size": target.stat().st_size, "sha256": sha256_file(target)})
    return rows


def _files_from_compose(compose_file: str, dest: Path) -> None:
    program = which("docker")
    dest.mkdir(parents=True, exist_ok=True)
    completed = run(
        [program, "compose", "-f", compose_file, "cp", "app:/data/files/.", str(dest)],
        os.environ.copy(),
    )
    if completed.returncode != 0:
        print("file_export_failed", file=sys.stderr)
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up the trial database and file directory together.")
    parser.add_argument("--out-dir", default="var/backups")
    parser.add_argument("--compose-file", default="")
    parser.add_argument("--files-from-compose", action="store_true")
    parser.add_argument("--encrypt", dest="encrypt", action="store_true", default=True)
    parser.add_argument("--no-encrypt", dest="encrypt", action="store_false")
    args = parser.parse_args(argv)
    phrase = _require_phrase(args.encrypt)
    if phrase:
        os.environ["K12_BACKUP_PASSPHRASE"] = phrase
    out_dir = Path(args.out_dir)
    with tempfile.TemporaryDirectory(prefix="k12-trial-backup-") as raw:
        work = Path(raw)
        dump = _dump_sql(work, args)
        files_root = work / "files"
        files_root.mkdir()
        if args.files_from_compose:
            if not args.compose_file:
                print("--files-from-compose needs --compose-file", file=sys.stderr)
                return 2
            _files_from_compose(args.compose_file, files_root)
            rows = _list_files(files_root)
        else:
            source = Path(os.environ.get("K12_FILE_DIR", "").strip())
            if not source.is_dir():
                print("K12_FILE_DIR is required", file=sys.stderr)
                return 2
            rows = _snapshot(source, files_root)
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "database_dump": "db.sql",
            "database_sha256": sha256_file(dump),
            "file_count": len(rows),
            "files": rows,
        }
        manifest_path = work / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        archive = work / f"k12-trial-{_stamp()}.tar.gz"
        with tarfile.open(archive, "w:gz") as packed:
            packed.add(dump, arcname="db.sql")
            packed.add(manifest_path, arcname="manifest.json")
            packed.add(files_root, arcname="files")
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.encrypt:
            final = out_dir / (archive.name + ".enc")
            try:
                openssl_convert(archive, final, decrypt=False)
            except RuntimeError as exc:
                final.unlink(missing_ok=True)
                print(redact(str(exc), [phrase]), file=sys.stderr)
                return 1
            archive.unlink(missing_ok=True)
        else:
            final = out_dir / archive.name
            shutil.copyfile(archive, final)
        print(f"BACKUP PASS encrypted={'yes' if args.encrypt else 'no'} files={len(rows)} archive={final}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
