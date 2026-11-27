"""Archive intake photos after N days. Log and session cleanup stay in retention_sweep.py.

This command needs a passphrase and an archive directory, so the daily retention
sweep does not delete intake bytes.
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.bootstrap.compose import build_logger  # noqa: E402
from backend.bootstrap.retention import days_of  # noqa: E402
from backend.practice.application.archive_intake import (  # noqa: E402
    ArchiveItem,
    check_unpacked,
    manifest_of,
    run_archive,
    safe_members,
    write_tree,
)
from scripts.trial_bundle import (  # noqa: E402
    database_name,
    is_dev_database,
    openssl_convert,
    passphrase,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    status = _dsn_status()
    if status == "invalid":
        print("K12_PG_DSN is invalid", file=sys.stderr)
        return 2
    if status == "k12":
        print("database k12 is refused", file=sys.stderr)
        return 2
    if args.verify_archive:
        return _verify(Path(args.verify_archive))
    raw_dir = os.environ.get("K12_FILE_DIR", "").strip()
    if not raw_dir:
        print("K12_FILE_DIR is required", file=sys.stderr)
        return 2
    directory = Path(raw_dir)
    if _unsafe_file_dir(directory):
        print("ARCHIVE REFUSED: unsafe file directory", file=sys.stderr)
        return 2
    if not directory.is_dir():
        print("K12_FILE_DIR is not a directory", file=sys.stderr)
        return 2
    encrypt = not args.no_encrypt
    if not args.dry_run and encrypt and not passphrase():
        print("K12_BACKUP_PASSPHRASE is required", file=sys.stderr)
        return 2
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        print("K12_PG_DSN is required", file=sys.stderr)
        return 2
    days = days_of(args.days or os.environ.get("K12_INTAKE_RETENTION_DAYS"), 30)
    now = datetime.now(timezone.utc)
    report = _run(dsn, directory, days=days, now=now, out_dir=Path(args.out_dir), encrypt=encrypt, dry_run=args.dry_run)
    if args.dry_run:
        print(
            f"ARCHIVE DRY-RUN confirmed={report.confirmed} superseded={report.superseded} bytes={report.total_bytes}"
        )
        return 0
    if report.code != 0:
        print("ARCHIVE FAILED", file=sys.stderr)
        return report.code
    print(f"ARCHIVE PASS eligible={report.eligible} archived={report.archived}")
    return 0


def _run(dsn: str, directory: Path, *, days: int, now: datetime, out_dir: Path, encrypt: bool, dry_run: bool):
    from psycopg_pool import ConnectionPool

    from backend.practice.adapters.pg_decision import PgDecisions
    from backend.practice.adapters.pg_files import PgFiles
    from backend.practice.adapters.pg_intake import PgIntake
    from backend.practice.adapters.pg_items import PgPracticeItems

    pool = ConnectionPool(dsn, min_size=1, max_size=1, open=True)
    try:
        return run_archive(
            PgIntake(pool),
            PgPracticeItems(pool),
            PgDecisions(pool),
            PgFiles(pool, directory),
            cutoff=now - timedelta(days=days),
            now=now,
            retention_days=days,
            out_dir=out_dir,
            encrypt=encrypt,
            dry_run=dry_run,
            logger=build_logger(),
            seal=_seal,
            opener=_open,
        )
    finally:
        pool.close()


def _verify(path: Path) -> int:
    if not path.is_file():
        print("archive is missing", file=sys.stderr)
        return 2
    encrypt = path.name.endswith(".enc")
    if encrypt and not passphrase():
        print("K12_BACKUP_PASSPHRASE is required", file=sys.stderr)
        return 2
    try:
        ok = _open(path, encrypt)
    except Exception:
        ok = False
    if not ok:
        print("ARCHIVE VERIFY FAILED", file=sys.stderr)
        return 1
    print("ARCHIVE VERIFIED")
    return 0


def _seal(
    items: tuple[ArchiveItem, ...],
    blobs: dict[str, bytes],
    now: datetime,
    cutoff: datetime,
    retention_days: int,
    out_dir: Path,
    encrypt: bool,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="k12-intake-archive-") as raw:
        plain = write_tree(
            Path(raw),
            manifest_of(items, archived_at=now, cutoff=cutoff, retention_days=retention_days),
            blobs,
        )
        dest = out_dir / f"k12-intake-archive-{_stamp()}{'.tar.gz.enc' if encrypt else '.tar.gz'}"
        try:
            if encrypt:
                openssl_convert(plain, dest, decrypt=False)
                plain.unlink(missing_ok=True)
                return dest
            dest.write_bytes(plain.read_bytes())
            return dest
        except Exception:
            dest.unlink(missing_ok=True)
            raise


def _open(path: Path, encrypt: bool) -> bool:
    with tempfile.TemporaryDirectory(prefix="k12-intake-verify-") as raw:
        work = Path(raw)
        tar_path = work / "bundle.tar.gz"
        if encrypt:
            openssl_convert(path, tar_path, decrypt=True)
        else:
            tar_path.write_bytes(path.read_bytes())
        unpacked = work / "unpacked"
        unpacked.mkdir()
        with tarfile.open(tar_path, "r:gz") as packed:
            names = [member.name for member in packed.getmembers()]
            if not safe_members(names):
                return False
            packed.extractall(unpacked, filter="data")
        return check_unpacked(unpacked)


def _dsn_status() -> str:
    dsn = os.environ.get("K12_PG_DSN", "").strip()
    if not dsn:
        return "empty"
    try:
        name = database_name(dsn)
    except Exception:
        return "invalid"
    if is_dev_database(name):
        return "k12"
    return "ok"


def _unsafe_file_dir(directory: Path) -> bool:
    resolved = directory.resolve()
    root = ROOT.resolve()
    if resolved == root or root.is_relative_to(resolved):
        return True
    return (resolved / ".git").exists()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive expired intake photos")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", default="")
    parser.add_argument("--out-dir", default="var/archives")
    parser.add_argument("--no-encrypt", action="store_true")
    parser.add_argument("--verify-archive", default="")
    return parser


if __name__ == "__main__":
    sys.exit(main())
