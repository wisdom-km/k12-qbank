"""Restore one trial backup after every SHA-256 in the manifest matches.

A target database named k12 is refused before any write. --verify-only decrypts,
unpacks, and checks the manifest, then writes nothing.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trial_bundle import (  # noqa: E402
    is_dev_database,
    openssl_convert,
    pg_env,
    redact,
    run,
    safe_relative,
    sha256_file,
    split_dsn,
    which,
)


def _phrase_ready() -> str:
    phrase = os.environ.get("K12_BACKUP_PASSPHRASE", "")
    if not phrase and sys.stdin.isatty() and sys.stdout.isatty():
        phrase = getpass.getpass("K12_BACKUP_PASSPHRASE: ")
        if phrase:
            os.environ["K12_BACKUP_PASSPHRASE"] = phrase
    return phrase


def _target_name(compose_file: str) -> str:
    if compose_file:
        name = os.environ.get("K12_PG_DATABASE", "").strip() or "k12_trial"
        return name
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        print("K12_PG_DSN is required", file=sys.stderr)
        raise SystemExit(2)
    try:
        return split_dsn(dsn)["name"]
    except RuntimeError:
        print("K12_PG_DSN is invalid", file=sys.stderr)
        raise SystemExit(2) from None


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _verify(bundle: Path) -> dict[str, object]:
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("manifest_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise RuntimeError("schema_version")
    dump_name = str(manifest.get("database_dump") or "")
    dump = bundle / safe_relative(dump_name)
    if not dump.is_file() or sha256_file(dump) != manifest.get("database_sha256"):
        raise RuntimeError("hash mismatch path=db.sql")
    rows = manifest.get("files")
    if not isinstance(rows, list) or manifest.get("file_count") != len(rows):
        raise RuntimeError("file_count")
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("file_count")
        relative = safe_relative(str(row.get("path") or ""))
        path = bundle / "files" / relative
        if not path.is_file():
            raise RuntimeError(f"hash mismatch path={relative.as_posix()}")
        if path.stat().st_size != row.get("size") or sha256_file(path) != row.get("sha256"):
            raise RuntimeError(f"hash mismatch path={relative.as_posix()}")
    return manifest


def _has_files(directory: Path) -> bool:
    return directory.exists() and any(item.is_file() for item in directory.rglob("*"))


def _clear_files(directory: Path) -> None:
    if not directory.exists():
        return
    for item in sorted((item for item in directory.rglob("*") if item.is_file()), reverse=True):
        item.unlink()


def _copy_files(bundle: Path, directory: Path, rows: list[dict[str, object]]) -> None:
    for row in rows:
        relative = safe_relative(str(row["path"]))
        dest = directory / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle / "files" / relative, dest)


def _restore_database(dump: Path, name: str, compose_file: str) -> None:
    sql = dump.read_bytes()
    if compose_file:
        program = which("docker")
        completed = run(
            [
                program,
                "compose",
                "-f",
                compose_file,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "k12",
                "-d",
                name,
                "-v",
                "ON_ERROR_STOP=1",
            ],
            os.environ.copy(),
            sql,
        )
    else:
        fields = split_dsn(os.environ["K12_PG_DSN"])
        program = which("psql")
        completed = run(
            [program, "-v", "ON_ERROR_STOP=1"],
            pg_env(os.environ.copy(), fields),
            sql,
        )
    if completed.returncode != 0:
        raise RuntimeError("psql_failed")


def _push_files(compose_file: str, directory: Path) -> None:
    program = which("docker")
    completed = run(
        [program, "compose", "-f", compose_file, "cp", f"{directory}/.", "app:/data/files"],
        os.environ.copy(),
    )
    if completed.returncode != 0:
        raise RuntimeError("file_import_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check and restore a trial backup.")
    parser.add_argument("archive")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--compose-file", default="")
    parser.add_argument("--files-to-compose", action="store_true")
    args = parser.parse_args(argv)
    archive = Path(args.archive)
    if not archive.is_file():
        print("archive is missing", file=sys.stderr)
        return 2
    name = ""
    if not args.verify_only:
        name = _target_name(args.compose_file)
        if is_dev_database(name):
            print("RESTORE REFUSED: database k12", file=sys.stderr)
            return 2
    encrypted = archive.name.endswith(".enc")
    if encrypted and not _phrase_ready():
        print("K12_BACKUP_PASSPHRASE is required", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="k12-trial-restore-") as raw:
        work = Path(raw)
        payload = archive
        if encrypted:
            payload = work / "bundle.tar.gz"
            try:
                openssl_convert(archive, payload, decrypt=True)
            except RuntimeError as exc:
                secret = os.environ.get("K12_BACKUP_PASSPHRASE", "")
                print(redact(str(exc), [secret]) or "decrypt_failed", file=sys.stderr)
                return 1
        bundle = work / "bundle"
        bundle.mkdir()
        try:
            with tarfile.open(payload, "r:gz") as packed:
                packed.extractall(bundle, filter="data")
            manifest = _verify(bundle)
        except (RuntimeError, tarfile.TarError, OSError, json.JSONDecodeError) as exc:
            return _fail(f"RESTORE FAIL: {exc}")
        count = int(manifest["file_count"])
        if args.verify_only:
            print(f"VERIFIED files={count} schema_version=1")
            return 0
        directory = Path(os.environ.get("K12_FILE_DIR", "").strip())
        if not str(directory):
            print("K12_FILE_DIR is required", file=sys.stderr)
            return 2
        if _has_files(directory) and not args.overwrite:
            print("RESTORE REFUSED: file directory is not empty", file=sys.stderr)
            return 2
        rows = manifest["files"]
        if not isinstance(rows, list):
            return _fail("RESTORE FAIL: file_count")
        try:
            dump_name = safe_relative(str(manifest["database_dump"]))
            _restore_database(bundle / dump_name, name, args.compose_file)
            directory.mkdir(parents=True, exist_ok=True)
            if args.overwrite:
                _clear_files(directory)
            _copy_files(bundle, directory, rows)
            if args.files_to_compose:
                if not args.compose_file:
                    print("--files-to-compose needs --compose-file", file=sys.stderr)
                    return 2
                _push_files(args.compose_file, directory)
        except RuntimeError as exc:
            return _fail(f"RESTORE FAIL: {exc}")
        print(f"RESTORED database={name} files={count}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
