"""List publication files. This read does not write an audit event."""

from __future__ import annotations

from backend.catalog.api import Publications
from backend.catalog.domain.publication import Asset

__all__ = ["list_publication_assets"]


def list_publication_assets(
    publications: Publications,
    publication_id: str,
) -> tuple[Asset, ...] | None:
    """Return the assets, or None when that publication does not exist."""
    return publications.list_assets(publication_id)
