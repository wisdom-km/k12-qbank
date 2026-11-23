"""Attach one publication file. Only a real insert is audited."""

from __future__ import annotations

import json
import time
from typing import Literal

from backend.catalog.api import Publications
from backend.catalog.domain.publication import AttachResult
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger


def attach_publication_asset(
    publications: Publications,
    publication_id: str,
    file_id: str,
    kind: Literal["image", "pdf"],
    checksum: str,
    size_bytes: int,
    mime_type: str,
    actor_id: str | None,
    logger: Logger,
    request_id: str | None = None,
) -> AttachResult:
    """Return the attach outcome. request_id stays off the port."""
    result = publications.attach_asset(
        publication_id,
        file_id,
        kind,
        checksum,
        size_bytes,
        mime_type,
        actor_id,  # type: ignore[arg-type]
    )
    asset = result.asset
    if result.result != "attached" or asset is None:
        return result
    detail = {
        "publication_id": asset.publication_id,
        "publication_asset_id": asset.publication_asset_id,
        "file_id": asset.file_id,
        "kind": asset.kind,
        "checksum": asset.checksum,
        "size_bytes": asset.size_bytes,
        "mime_type": asset.mime_type,
    }
    logger.log(
        LogEvent(
            time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            level="INFO",
            event="publication_asset_attached",
            request_id="" if request_id is None else request_id,
            module="catalog.publication",
            outcome="ok",
            duration_ms=0,
            actor_user_id="" if actor_id is None else actor_id,
            target_kind="publication_asset",
            target_id=asset.publication_asset_id,
            audit=True,
            action="publication_asset_attached",
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )
    return result
