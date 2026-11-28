"""Save and read one intake page. The browser's paper id is checked again here."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok, StoreFault
from backend.kernel.use_log import emit
from backend.practice.domain.intake_image import content_type_of, image_kind, strip_jpeg_capture
from backend.practice.domain.intake_page import IntakePage, paper_page_count
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import Paper
from backend.practice.domain.qr_code import parse_qr_payload

_MODULE = "practice.intake"
_KINDS = {"image/jpeg": "jpeg", "image/png": "png"}
_LOCATED = {"qr", "manual"}


def intake_max_bytes() -> int:
    """K12_INTAKE_MAX_BYTES, or 10 MiB when the value is missing or not a positive integer."""
    raw = os.environ.get("K12_INTAKE_MAX_BYTES", "").strip()
    if not raw:
        return 10 * 1024 * 1024
    try:
        value = int(raw)
    except ValueError:
        return 10 * 1024 * 1024
    if value < 1:
        return 10 * 1024 * 1024
    return value


def pages_of(paper: Paper, items: Sequence[PracticeItem]) -> int:
    return paper_page_count(
        paper.layout_kind,
        paper.slots_per_page,
        tuple(item.page_no for item in items),
    )


def upload_intake(
    *,
    paper_id: str,
    page_no: int,
    body: bytes,
    content_type: str,
    located_by: str,
    qr_text: str,
    replace: bool,
    actor_id: str,
    actor_role: str,
    practice: object,
    items: object,
    files: object,
    intake: object,
    logger: Logger,
    request_id: str,
) -> Ok[dict[str, object]] | Err:
    started = time.perf_counter()
    if located_by not in _LOCATED:
        return _refuse(logger, request_id, started, "validation_failed", "validation_failed")
    kind = _KINDS.get(content_type)
    if kind is None:
        return _refuse(logger, request_id, started, "not_image", "not_image")
    if len(body) > intake_max_bytes():
        return _refuse(logger, request_id, started, "too_large", "too_large")
    if actor_role not in {"admin", "teacher"}:
        return _refuse(logger, request_id, started, "permission_denied", "permission_denied")
    paper = practice.get_paper(paper_id)  # type: ignore[attr-defined]
    if paper is None:
        return _refuse(logger, request_id, started, "paper_not_found", "paper_not_found")
    if not _allows(actor_role, actor_id, paper):
        return _refuse(logger, request_id, started, "permission_denied", "permission_denied")
    count = pages_of(paper, items.items_of(paper_id))  # type: ignore[attr-defined]
    if page_no < 1 or page_no > count:
        return _refuse(logger, request_id, started, "page_out_of_range", "page_out_of_range")
    if located_by == "qr":
        parsed = parse_qr_payload(qr_text)
        if parsed is None or parsed != (paper_id, page_no):
            return _refuse(logger, request_id, started, "qr_mismatch", "qr_mismatch")
    seen = image_kind(body)
    if seen != kind:
        return _refuse(logger, request_id, started, "not_image", "not_image")
    stored = strip_jpeg_capture(body) if seen == "jpeg" else body
    if image_kind(stored) != seen or len(stored) > intake_max_bytes():
        return _refuse(logger, request_id, started, "not_image", "not_image")
    digest = hashlib.sha256(stored).hexdigest()
    file_id = "file-" + digest[:16]
    purpose = intake.file_purpose(file_id)  # type: ignore[attr-defined]
    if purpose not in {None, "intake"}:
        return _refuse(logger, request_id, started, "file_purpose_conflict", "file_purpose_conflict")
    current = intake.current(paper_id, page_no)  # type: ignore[attr-defined]
    if current is not None and not replace:
        return _refuse(logger, request_id, started, "page_already_received", "page_already_received")
    files.store_bytes(file_id, stored)  # type: ignore[attr-defined]
    row = IntakePage(
        intake_id="intake-" + uuid.uuid4().hex,
        paper_id=paper_id,
        page_no=page_no,
        file_id=file_id,
        checksum=digest,
        uploaded_by=actor_id,
        uploaded_at=_now(),
        located_by=located_by,
    )
    try:
        intake.place(row, replace=replace)  # type: ignore[attr-defined]
    except StoreFault as fault:
        return _refuse(logger, request_id, started, fault.code, fault.code)
    except Exception:
        emit(
            logger,
            level="ERROR",
            event="use_case_failed",
            request_id=request_id,
            module=_MODULE,
            outcome="store_failed",
            started=started,
        )
        return Err("store_failed", "the store failed")
    _audit(
        logger,
        request_id,
        started,
        "intake_uploaded",
        actor_id,
        actor_role,
        paper_id,
        page_no,
        located_by,
        replace,
    )
    return Ok(
        {
            "intake_id": row.intake_id,
            "paper_id": paper_id,
            "page_no": page_no,
            "file_id": file_id,
            "located_by": located_by,
            "replaced": replace and current is not None,
        }
    )


def intake_status(
    *,
    paper_id: str,
    actor_id: str,
    actor_role: str,
    practice: object,
    items: object,
    intake: object,
    logger: Logger,
    request_id: str,
) -> Ok[dict[str, object]] | Err:
    started = time.perf_counter()
    if actor_role not in {"admin", "teacher"}:
        return _refuse(logger, request_id, started, "permission_denied", "permission_denied")
    paper = practice.get_paper(paper_id)  # type: ignore[attr-defined]
    if paper is None:
        return _refuse(logger, request_id, started, "paper_not_found", "paper_not_found")
    if not _allows(actor_role, actor_id, paper):
        return _refuse(logger, request_id, started, "permission_denied", "permission_denied")
    count = pages_of(paper, items.items_of(paper_id))  # type: ignore[attr-defined]
    found = {row.page_no: row for row in intake.currents(paper_id)}  # type: ignore[attr-defined]
    pages: list[dict[str, object]] = []
    for number in range(1, count + 1):
        row = found.get(number)
        pages.append(
            {
                "page_no": number,
                "received": row is not None,
                "uploaded_at": None if row is None else row.uploaded_at,
                "located_by": None if row is None else row.located_by,
                "intake_id": None if row is None else row.intake_id,
            }
        )
    return Ok({"paper_id": paper_id, "page_count": count, "pages": pages})


def read_intake_image(
    *,
    intake_id: str,
    actor_id: str,
    actor_role: str,
    practice: object,
    files: object,
    intake: object,
    logger: Logger,
    request_id: str,
) -> Ok[tuple[bytes, str]] | Err:
    started = time.perf_counter()
    if actor_role not in {"admin", "teacher"}:
        return _refuse(logger, request_id, started, "permission_denied", "permission_denied")
    row = intake.get(intake_id)  # type: ignore[attr-defined]
    if row is None:
        return _refuse(logger, request_id, started, "not_found", "not_found")
    paper = practice.get_paper(row.paper_id)  # type: ignore[attr-defined]
    if paper is None or not _allows(actor_role, actor_id, paper):
        return _refuse(logger, request_id, started, "permission_denied", "permission_denied")
    if row.archived_at:
        return _refuse(logger, request_id, started, "intake_archived", "收卷照片已到期归档")
    data = files.read(row.file_id)  # type: ignore[attr-defined]
    if data is None:
        return _refuse(logger, request_id, started, "file_missing", "file_missing")
    kind = image_kind(data)
    if kind is None:
        return _refuse(logger, request_id, started, "not_image", "not_image")
    _audit(
        logger,
        request_id,
        started,
        "intake_read",
        actor_id,
        actor_role,
        row.paper_id,
        row.page_no,
        row.located_by,
        False,
    )
    return Ok((data, content_type_of(kind)))


def _allows(actor_role: str, actor_id: str, paper: Paper) -> bool:
    if actor_role == "admin":
        return True
    return actor_role == "teacher" and paper.teacher_id == actor_id


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(
    logger: Logger,
    request_id: str,
    started: float,
    event: str,
    actor_id: str,
    actor_role: str,
    paper_id: str,
    page_no: int,
    located_by: str,
    replaced: bool,
) -> None:
    detail = json.dumps(
        {
            "paper_id": paper_id,
            "page_no": page_no,
            "located_by": located_by,
            "replaced": replaced,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    emit(
        logger,
        level="INFO",
        event=event,
        request_id=request_id,
        module=_MODULE,
        outcome="ok",
        started=started,
        actor_user_id=actor_id,
        target_kind="paper",
        target_id=paper_id,
        audit=True,
        detail=detail,
        action=event,
        actor_role=actor_role,
    )


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module=_MODULE,
        outcome=code,
        started=started,
    )
    return Err(code, message)
