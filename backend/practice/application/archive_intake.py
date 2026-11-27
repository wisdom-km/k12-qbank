"""Choose intake photos that are old enough to archive. No SQL in this file."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.kernel.logger import Logger
from backend.kernel.use_log import emit

_MODULE = "practice"
_FILE_ID = re.compile(r"files/file-[0-9a-f]{16}\Z")


@dataclass(frozen=True)
class PageView:
    intake_id: str
    paper_id: str
    page_no: int
    file_id: str
    checksum: str
    purpose: str
    superseded_at: datetime | None
    archived_at: datetime | None


@dataclass(frozen=True)
class PaperClock:
    item_count: int
    open_decisions: int
    latest: datetime | None


@dataclass(frozen=True)
class ArchiveItem:
    intake_id: str
    paper_id: str
    page_no: int
    file_id: str
    checksum: str
    size: int
    reason: str


@dataclass(frozen=True)
class ArchiveReport:
    code: int
    confirmed: int
    superseded: int
    eligible: int
    archived: int
    deleted: int
    total_bytes: int
    archive: Path | None = None


def parse_stamp(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_eligible(
    pages: tuple[PageView, ...] | list[PageView],
    clocks: dict[str, PaperClock],
    cutoff: datetime,
) -> tuple[ArchiveItem, ...]:
    """Confirmed papers and replaced photos only. Page PDFs stay out."""
    chosen: list[ArchiveItem] = []
    limit = cutoff.astimezone(timezone.utc)
    for page in pages:
        if page.archived_at is not None or page.purpose != "intake":
            continue
        if page.superseded_at is not None:
            if page.superseded_at.astimezone(timezone.utc) <= limit:
                chosen.append(_item(page, "superseded"))
            continue
        clock = clocks.get(page.paper_id)
        if clock is None or clock.item_count < 1 or clock.open_decisions != clock.item_count:
            continue
        if clock.latest is None or clock.latest.astimezone(timezone.utc) > limit:
            continue
        chosen.append(_item(page, "confirmed"))
    chosen.sort(key=lambda row: (row.paper_id, row.page_no, row.intake_id))
    return tuple(chosen)


def clocks_for(pages: tuple[PageView, ...] | list[PageView], items: object, decisions: object) -> dict[str, PaperClock]:
    found: dict[str, PaperClock] = {}
    for page in pages:
        if page.paper_id in found:
            continue
        current = decisions.currents(page.paper_id)  # type: ignore[attr-defined]
        latest: datetime | None = None
        for row in current:
            stamp = parse_stamp(str(row.decided_at))
            if stamp is not None and (latest is None or stamp > latest):
                latest = stamp
        found[page.paper_id] = PaperClock(
            item_count=len(items.items_of(page.paper_id)),  # type: ignore[attr-defined]
            open_decisions=len(current),
            latest=latest,
        )
    return found


def views_of(intake: object, files: object) -> tuple[PageView, ...]:
    rows: list[PageView] = []
    for page in intake.unarchived():  # type: ignore[attr-defined]
        purpose = files.purpose(page.file_id)  # type: ignore[attr-defined]
        rows.append(
            PageView(
                intake_id=str(page.intake_id),
                paper_id=str(page.paper_id),
                page_no=int(page.page_no),
                file_id=str(page.file_id),
                checksum=str(page.checksum),
                purpose="" if purpose is None else str(purpose),
                superseded_at=parse_stamp(page.superseded_at),
                archived_at=parse_stamp(page.archived_at),
            )
        )
    return tuple(rows)


def plan(
    intake: object,
    items: object,
    decisions: object,
    files: object,
    cutoff: datetime,
) -> tuple[ArchiveItem, ...]:
    pages = views_of(intake, files)
    return select_eligible(pages, clocks_for(pages, items, decisions), cutoff)


def run_archive(
    intake: object,
    items: object,
    decisions: object,
    files: object,
    *,
    cutoff: datetime,
    now: datetime,
    retention_days: int,
    out_dir: Path,
    encrypt: bool,
    dry_run: bool,
    logger: Logger,
    seal: Callable[[tuple[ArchiveItem, ...], dict[str, bytes], datetime, datetime, int, Path, bool], Path],
    opener: Callable[[Path, bool], bool],
) -> ArchiveReport:
    """Pack, check the archive, then mark and delete. A failed check writes nothing."""
    chosen = plan(intake, items, decisions, files, cutoff)
    confirmed = sum(1 for row in chosen if row.reason == "confirmed")
    superseded = sum(1 for row in chosen if row.reason == "superseded")
    total = _measure(files, chosen)
    if dry_run:
        return ArchiveReport(0, confirmed, superseded, len(chosen), 0, 0, total)
    if not chosen:
        return ArchiveReport(0, 0, 0, 0, 0, 0, 0)
    loaded = _blobs(files, chosen)
    if loaded is None:
        return ArchiveReport(1, confirmed, superseded, len(chosen), 0, 0, total)
    blobs, sizes = loaded
    packed = tuple(
        ArchiveItem(
            row.intake_id,
            row.paper_id,
            row.page_no,
            row.file_id,
            row.checksum,
            sizes[row.file_id],
            row.reason,
        )
        for row in chosen
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    archive: Path | None = None
    try:
        archive = seal(packed, blobs, now, cutoff, retention_days, out_dir, encrypt)
        if not opener(archive, encrypt):
            archive.unlink(missing_ok=True)
            return ArchiveReport(1, confirmed, superseded, len(packed), 0, 0, total, None)
    except Exception:
        if archive is not None:
            archive.unlink(missing_ok=True)
        return ArchiveReport(1, confirmed, superseded, len(packed), 0, 0, total, None)
    intake.mark_archived(tuple(row.intake_id for row in packed), stamp_text(now))  # type: ignore[attr-defined]
    deleted = 0
    for row in packed:
        if intake.count_open_file(row.file_id) > 0:  # type: ignore[attr-defined]
            continue
        if files.delete_online_bytes(row.file_id):  # type: ignore[attr-defined]
            deleted += 1
    _logged(logger, len(packed), len(packed), deleted, retention_days)
    return ArchiveReport(0, confirmed, superseded, len(packed), len(packed), deleted, total, archive)


def manifest_of(
    items: tuple[ArchiveItem, ...],
    *,
    archived_at: datetime,
    cutoff: datetime,
    retention_days: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "archived_at": stamp_text(archived_at),
        "retention_days": retention_days,
        "cutoff": stamp_text(cutoff),
        "item_count": len(items),
        "items": [
            {
                "intake_id": row.intake_id,
                "paper_id": row.paper_id,
                "page_no": row.page_no,
                "file_id": row.file_id,
                "checksum": row.checksum,
                "size": row.size,
                "reason": row.reason,
            }
            for row in items
        ],
    }


def write_tree(directory: Path, document: dict[str, object], blobs: dict[str, bytes]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "archive-manifest.json"
    manifest_path.write_text(json.dumps(document, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
    files = directory / "files"
    files.mkdir()
    for file_id, data in blobs.items():
        (files / file_id).write_bytes(data)
    archive = directory / "bundle.tar.gz"
    with tarfile.open(archive, "w:gz") as packed:
        packed.add(manifest_path, arcname="archive-manifest.json")
        for file_id in blobs:
            packed.add(files / file_id, arcname=f"files/{file_id}")
    return archive


def check_unpacked(directory: Path) -> bool:
    manifest_path = directory / "archive-manifest.json"
    if not manifest_path.is_file():
        return False
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = document.get("items")
    if not isinstance(rows, list) or document.get("item_count") != len(rows):
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        file_id = str(row.get("file_id", ""))
        path = directory / "files" / file_id
        if not path.is_file():
            return False
        data = path.read_bytes()
        if len(data) != int(row.get("size", -1)):
            return False
        if hashlib.sha256(data).hexdigest() != str(row.get("checksum", "")):
            return False
    return True


def safe_members(names: list[str]) -> bool:
    for name in names:
        if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name:
            return False
        if name != "archive-manifest.json" and _FILE_ID.fullmatch(name) is None:
            return False
    return True


def _item(page: PageView, reason: str) -> ArchiveItem:
    return ArchiveItem(page.intake_id, page.paper_id, page.page_no, page.file_id, page.checksum, 0, reason)


def _measure(files: object, chosen: tuple[ArchiveItem, ...]) -> int:
    total = 0
    seen: set[str] = set()
    for row in chosen:
        if row.file_id in seen:
            continue
        seen.add(row.file_id)
        data = files.read(row.file_id)  # type: ignore[attr-defined]
        if isinstance(data, (bytes, bytearray)):
            total += len(data)
    return total


def _blobs(
    files: object,
    chosen: tuple[ArchiveItem, ...],
) -> tuple[dict[str, bytes], dict[str, int]] | None:
    blobs: dict[str, bytes] = {}
    sizes: dict[str, int] = {}
    for row in chosen:
        data = files.read(row.file_id)  # type: ignore[attr-defined]
        if not isinstance(data, (bytes, bytearray)):
            return None
        raw = bytes(data)
        if hashlib.sha256(raw).hexdigest() != row.checksum:
            return None
        blobs[row.file_id] = raw
        sizes[row.file_id] = len(raw)
    return blobs, sizes


def _logged(logger: Logger, eligible: int, archived: int, deleted: int, retention_days: int) -> None:
    emit(
        logger,
        level="INFO",
        event="intake_archived",
        request_id="archive",
        module=_MODULE,
        outcome="ok",
        started=time.perf_counter(),
        detail=json.dumps(
            {
                "eligible": eligible,
                "archived": archived,
                "deleted_files": deleted,
                "retention_days": retention_days,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )
