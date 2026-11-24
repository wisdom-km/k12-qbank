"""One published binding. Explicit publish may store layout_template_id."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from backend.kernel.result import StoreFault

# The id is a hash of the publication and the checksum. checksum[:16] alone
# would collide when two publications carry the same file.
_ASSET_PREFIX = "pubasset-"
PUBFILE_ID = re.compile(r"^pubfile-[0-9a-f]{16}$")
IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})
PDF_MIMES = frozenset({"application/pdf"})


class RetireCode(str):
    """One of retired, already_retired, not_found. The id is set only for retired."""

    def __new__(
        cls,
        code: str,
        publication_id: str | None = None,
        subject_id: str | None = None,
    ) -> RetireCode:
        value = str.__new__(cls, code)
        value.publication_id = publication_id
        value.subject_id = subject_id
        return value

    publication_id: str | None
    subject_id: str | None


@dataclass(frozen=True)
class Publication:
    publication_id: str
    question_version_id: str
    answer_version_id: str
    subject_id: str
    status: str
    layout_template_id: str | None = None


def require_actor(actor: str | None) -> None:
    """An empty actor never retires a binding and never reaches the audit sink."""
    if not isinstance(actor, str) or not actor.strip():
        raise StoreFault("invalid_actor")


def require_subject(subject_id: str | None) -> None:
    """The subject copied from the approval row must be non-empty."""
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise StoreFault("invalid_subject")


def bound_page(offset: int, limit: int) -> tuple[int, int]:
    """Clamp a list page. The numbers match the audit list: offset below 0 becomes 0, limit below 1 becomes 1, limit above 200 becomes 200."""
    if offset < 0:
        offset = 0
    if limit < 1:
        limit = 1
    elif limit > 200:
        limit = 200
    return offset, limit


def clean_layout(layout_template_id: str | None) -> str | None:
    """A blank layout is stored as NULL. There is no layout catalog yet."""
    if not isinstance(layout_template_id, str):
        return None
    text = layout_template_id.strip()
    if not text:
        return None
    return text


@dataclass(frozen=True)
class Asset:
    publication_asset_id: str
    publication_id: str
    file_id: str
    kind: str
    checksum: str
    size_bytes: int
    mime_type: str
    created_at: datetime
    created_by: str


@dataclass(frozen=True)
class AttachResult:
    result: str
    publication_asset_id: str | None = None
    asset: Asset | None = None


@dataclass(frozen=True)
class RemoveResult:
    result: str
    asset: Asset | None = None


def asset_id_for(publication_id: str, checksum: str) -> str:
    """Stable id for one publication and checksum. A repeat returns the same id."""
    digest = hashlib.sha256(f"{publication_id}\n{checksum}".encode()).hexdigest()[:16]
    return _ASSET_PREFIX + digest


def mime_allowed(kind: str, mime_type: str) -> bool:
    """Kind chooses the whitelist. The database does not store this map."""
    if kind == "image":
        return mime_type in IMAGE_MIMES
    if kind == "pdf":
        return mime_type in PDF_MIMES
    return False


def asset_file_refusal(
    file_id: str,
    kind: str,
    mime_type: str,
    *,
    page_file: bool,
    paper_file: bool,
    paper_checksum: bool,
    intake_file: bool = False,
) -> str | None:
    """Refuse a page photo, an intake photo, or an issued-paper file.

    A file- prefix is a page file even when it also fails the pubfile shape.
    purpose=intake is refused even when the id is shaped like a publication file.
    """
    if intake_file:
        return "intake_file_rejected"
    if file_id.startswith("file-"):
        return "page_file_rejected"
    if page_file:
        return "page_file_rejected"
    if paper_file:
        return "paper_file_rejected"
    if paper_checksum:
        return "paper_file_rejected"
    if PUBFILE_ID.fullmatch(file_id) is None:
        return "invalid_file_id"
    if not mime_allowed(kind, mime_type):
        return "disallowed_mime"
    return None
