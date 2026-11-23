"""Remove one publication file. Only a real delete is audited."""

from __future__ import annotations

import json
import time

from backend.catalog.api import Publications
from backend.catalog.domain.publication import RemoveResult
from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger


def remove_publication_asset(
    publications: Publications,
    publication_id: str,
    publication_asset_id: str,
    actor_id: str | None,
    logger: Logger,
    request_id: str | None = None,
) -> RemoveResult:
    """Return removed or not_found. request_id stays off the port."""
    result = publications.remove_asset(
        publication_id,
        publication_asset_id,
        actor_id,  # type: ignore[arg-type]
    )
    asset = result.asset
    if result.result != "removed" or asset is None:
        return result
    detail = {
        "publication_id": asset.publication_id,
        "publication_asset_id": asset.publication_asset_id,
        "file_id": asset.file_id,
        "kind": asset.kind,
        "checksum": asset.checksum,
    }
    logger.log(
        LogEvent(
            time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            level="INFO",
            event="publication_asset_removed",
            request_id="" if request_id is None else request_id,
            module="catalog.publication",
            outcome="ok",
            duration_ms=0,
            actor_user_id="" if actor_id is None else actor_id,
            target_kind="publication_asset",
            target_id=asset.publication_asset_id,
            audit=True,
            action="publication_asset_removed",
            detail=json.dumps(detail, ensure_ascii=False),
        )
    )
    return result
