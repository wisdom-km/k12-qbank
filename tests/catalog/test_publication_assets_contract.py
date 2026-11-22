"""Publication asset contract. Memory always runs. PostgreSQL runs when K12_PG_DSN is set."""

from __future__ import annotations

import json
import os
import time
import unittest

from backend.catalog.adapters.memory_publications import MemoryPublications
from backend.catalog.application.attach_publication_asset import attach_publication_asset
from backend.catalog.application.list_publication_assets import list_publication_assets
from backend.catalog.application.remove_publication_asset import remove_publication_asset
from backend.catalog.domain.publication import Publication, asset_id_for
from backend.kernel.log_event import LogEvent

_ACTOR = "actor-d8a"
_FILE = "pubfile-0123456789abcdef"
_FILE_TWO = "pubfile-fedcba9876543210"
_PAGE_FILE = "pubfile-bbbbbbbbbbbbbbbb"
_PAPER_FILE = "pubfile-cccccccccccccccc"


class PublicationAssetCases:
    publications: object

    def tearDown(self) -> None:
        self.publications.clear_privacy_notes()  # type: ignore[attr-defined]

    def test_attach_success(self) -> None:
        self._put("pub-d8a-ok")
        result = self._attach("pub-d8a-ok", _FILE, "image", "checksum-ok", 12, "image/png")
        self.assertEqual(result.result, "attached")
        self.assertEqual(result.publication_asset_id, asset_id_for("pub-d8a-ok", "checksum-ok"))
        rows = self._list("pub-d8a-ok")
        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].file_id, _FILE)
        self.assertEqual(rows[0].kind, "image")
        self.assertEqual(rows[0].checksum, "checksum-ok")
        self.assertEqual(rows[0].size_bytes, 12)
        self.assertEqual(rows[0].mime_type, "image/png")
        self.assertEqual(rows[0].created_by, _ACTOR)

    def test_invalid_file_id(self) -> None:
        self._put("pub-d8a-bad")
        result = self._attach("pub-d8a-bad", "not-a-pubfile", "image", "checksum-bad", 4, "image/png")
        self.assertEqual(result.result, "invalid_file_id")
        self.assertIsNone(result.publication_asset_id)
        self.assertEqual(self._list("pub-d8a-bad"), ())

    def test_same_checksum_twice_is_already_attached(self) -> None:
        self._put("pub-d8a-dup")
        first = self._attach("pub-d8a-dup", _FILE, "image", "checksum-dup", 8, "image/png")
        second = self._attach("pub-d8a-dup", _FILE_TWO, "pdf", "checksum-dup", 9, "application/pdf")
        self.assertEqual(first.result, "attached")
        self.assertEqual(second.result, "already_attached")
        self.assertEqual(second.publication_asset_id, first.publication_asset_id)
        rows = self._list("pub-d8a-dup")
        assert rows is not None
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].file_id, _FILE)

    def test_same_checksum_on_two_publications_both_attach(self) -> None:
        self._put("pub-d8a-left")
        self._put("pub-d8a-right")
        left = self._attach("pub-d8a-left", _FILE, "image", "checksum-shared", 3, "image/jpeg")
        right = self._attach("pub-d8a-right", _FILE, "image", "checksum-shared", 3, "image/jpeg")
        self.assertEqual(left.result, "attached")
        self.assertEqual(right.result, "attached")
        self.assertNotEqual(left.publication_asset_id, right.publication_asset_id)
        self.assertEqual(left.publication_asset_id, asset_id_for("pub-d8a-left", "checksum-shared"))
        self.assertEqual(right.publication_asset_id, asset_id_for("pub-d8a-right", "checksum-shared"))

    def test_missing_publication(self) -> None:
        result = self._attach("pub-d8a-missing", _FILE, "image", "checksum-miss", 1, "image/webp")
        self.assertEqual(result.result, "publication_not_found")
        self.assertIsNone(self._list("pub-d8a-missing"))

    def test_retired_publication_refuses_attach(self) -> None:
        self._put("pub-d8a-old", "retired")
        result = self._attach("pub-d8a-old", _FILE, "pdf", "checksum-old", 20, "application/pdf")
        self.assertEqual(result.result, "publication_retired")
        self.assertEqual(self._list("pub-d8a-old"), ())

    def test_image_rejects_pdf_mime(self) -> None:
        self._put("pub-d8a-mime")
        result = self._attach("pub-d8a-mime", _FILE, "image", "checksum-mime", 5, "application/pdf")
        self.assertEqual(result.result, "disallowed_mime")

    def test_pdf_rejects_png_mime(self) -> None:
        self._put("pub-d8a-mime-pdf")
        result = self._attach("pub-d8a-mime-pdf", _FILE, "pdf", "checksum-mime-pdf", 5, "image/png")
        self.assertEqual(result.result, "disallowed_mime")

    def test_file_prefix_is_page_file_rejected(self) -> None:
        self._put("pub-d8a-page")
        result = self._attach("pub-d8a-page", "file-0123456789abcdef", "image", "checksum-page", 6, "image/png")
        self.assertEqual(result.result, "page_file_rejected")

    def test_file_prefix_wins_over_the_shape_check(self) -> None:
        self._put("pub-d8a-prefix")
        result = self._attach("pub-d8a-prefix", "file-short", "image", "checksum-prefix", 6, "image/png")
        self.assertEqual(result.result, "page_file_rejected")

    def test_files_purpose_page_is_rejected(self) -> None:
        self._put("pub-d8a-purpose")
        self.publications.note_page_file(_PAGE_FILE)  # type: ignore[attr-defined]
        result = self._attach("pub-d8a-purpose", _PAGE_FILE, "image", "checksum-purpose", 7, "image/png")
        self.assertEqual(result.result, "page_file_rejected")

    def test_paper_file_id_is_rejected(self) -> None:
        self._put("pub-d8a-paper")
        self.publications.note_paper_file(_PAPER_FILE)  # type: ignore[attr-defined]
        result = self._attach("pub-d8a-paper", _PAPER_FILE, "pdf", "checksum-paper-file", 11, "application/pdf")
        self.assertEqual(result.result, "paper_file_rejected")

    def test_paper_checksum_is_rejected(self) -> None:
        self._put("pub-d8a-sum")
        self.publications.note_paper_checksum("checksum-from-paper")  # type: ignore[attr-defined]
        result = self._attach("pub-d8a-sum", _FILE, "image", "checksum-from-paper", 11, "image/webp")
        self.assertEqual(result.result, "paper_file_rejected")

    def test_remove_success_drops_the_row(self) -> None:
        self._put("pub-d8a-rm")
        attached = self._attach("pub-d8a-rm", _FILE, "image", "checksum-rm", 2, "image/png")
        assert attached.publication_asset_id is not None
        removed = self._remove("pub-d8a-rm", attached.publication_asset_id)
        self.assertEqual(removed.result, "removed")
        self.assertEqual(self._list("pub-d8a-rm"), ())

    def test_remove_missing_is_not_found(self) -> None:
        self._put("pub-d8a-gone")
        removed = self._remove("pub-d8a-gone", "pubasset-0123456789abcdef")
        self.assertEqual(removed.result, "not_found")

    def test_remove_under_another_publication_keeps_the_row(self) -> None:
        self._put("pub-d8a-home")
        self._put("pub-d8a-other")
        attached = self._attach("pub-d8a-home", _FILE, "image", "checksum-home", 2, "image/png")
        assert attached.publication_asset_id is not None
        removed = self._remove("pub-d8a-other", attached.publication_asset_id)
        self.assertEqual(removed.result, "not_found")
        rows = self._list("pub-d8a-home")
        assert rows is not None
        self.assertEqual(len(rows), 1)

    def test_remove_still_works_after_retire(self) -> None:
        self._put("pub-d8a-retire")
        attached = self._attach("pub-d8a-retire", _FILE, "pdf", "checksum-retire", 15, "application/pdf")
        assert attached.publication_asset_id is not None
        code = self.publications.retire_by_binding("q-pub-d8a-retire", "a-pub-d8a-retire", _ACTOR)  # type: ignore[attr-defined]
        self.assertEqual(code, "retired")
        removed = self._remove("pub-d8a-retire", attached.publication_asset_id)
        self.assertEqual(removed.result, "removed")
        self.assertEqual(self._list("pub-d8a-retire"), ())

    def test_list_empty(self) -> None:
        self._put("pub-d8a-empty")
        self.assertEqual(self._list("pub-d8a-empty"), ())

    def test_list_orders_by_created_at_then_id(self) -> None:
        publication_id = "pub-d8a-order"
        self._put(publication_id)
        first_checksum, second_checksum = _opposed_checksums(publication_id)
        first = self._attach(publication_id, _FILE, "image", first_checksum, 1, "image/png")
        time.sleep(0.02)
        second = self._attach(publication_id, _FILE_TWO, "image", second_checksum, 1, "image/jpeg")
        self.assertEqual(first.result, "attached")
        self.assertEqual(second.result, "attached")
        rows = self._list(publication_id)
        assert rows is not None
        ordered = tuple(sorted(rows, key=lambda asset: (asset.created_at, asset.publication_asset_id)))
        self.assertEqual(rows, ordered)
        self.assertLess(rows[0].created_at, rows[1].created_at)
        self.assertGreater(rows[0].publication_asset_id, rows[1].publication_asset_id)

    def _put(self, publication_id: str, status: str = "active") -> None:
        self.publications.put(  # type: ignore[attr-defined]
            Publication(
                publication_id=publication_id,
                question_version_id=f"q-{publication_id}",
                answer_version_id=f"a-{publication_id}",
                subject_id="subj-d8a",
                status=status,
            )
        )

    def _attach(
        self,
        publication_id: str,
        file_id: str,
        kind: str,
        checksum: str,
        size_bytes: int,
        mime_type: str,
    ) -> object:
        return self.publications.attach_asset(  # type: ignore[attr-defined, no-any-return]
            publication_id,
            file_id,
            kind,
            checksum,
            size_bytes,
            mime_type,
            _ACTOR,
        )

    def _remove(self, publication_id: str, publication_asset_id: str) -> object:
        return self.publications.remove_asset(  # type: ignore[attr-defined, no-any-return]
            publication_id,
            publication_asset_id,
            _ACTOR,
        )

    def _list(self, publication_id: str) -> object:
        return self.publications.list_assets(publication_id)  # type: ignore[attr-defined, no-any-return]


class MemoryPublicationAssetTest(PublicationAssetCases, unittest.TestCase):
    def setUp(self) -> None:
        self.publications = MemoryPublications()


class PgPublicationAssetTest(PublicationAssetCases, unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from backend.catalog.adapters.pg_publications import PgPublications

        self.pool = _pool()
        _execute(self.pool, "TRUNCATE TABLE publication RESTART IDENTITY CASCADE")
        self.publications = PgPublications(self.pool)
        self.publications.clear_privacy_notes()


class PublicationAssetAuditTest(unittest.TestCase):
    def test_only_a_real_attach_and_remove_are_audited(self) -> None:
        publications = MemoryPublications()
        publications.put(
            Publication(
                publication_id="pub-d8a-audit",
                question_version_id="q-pub-d8a-audit",
                answer_version_id="a-pub-d8a-audit",
                subject_id="subj-d8a",
                status="active",
            )
        )
        logger = _Capture()
        attached = attach_publication_asset(
            publications,
            "pub-d8a-audit",
            _FILE,
            "image",
            "checksum-audit",
            4,
            "image/png",
            _ACTOR,
            logger,
            request_id="req-d8a",
        )
        again = attach_publication_asset(
            publications,
            "pub-d8a-audit",
            _FILE_TWO,
            "image",
            "checksum-audit",
            4,
            "image/png",
            _ACTOR,
            logger,
            request_id="req-d8a",
        )
        self.assertEqual(attached.result, "attached")
        self.assertEqual(again.result, "already_attached")
        self.assertEqual([event.action for event in logger.events], ["publication_asset_attached"])
        detail = json.loads(logger.events[0].detail)
        self.assertEqual(
            detail,
            {
                "publication_id": "pub-d8a-audit",
                "publication_asset_id": attached.publication_asset_id,
                "file_id": _FILE,
                "kind": "image",
                "checksum": "checksum-audit",
                "size_bytes": 4,
                "mime_type": "image/png",
            },
        )
        self.assertEqual(logger.events[0].target_kind, "publication_asset")
        self.assertEqual(logger.events[0].target_id, attached.publication_asset_id)
        self.assertTrue(logger.events[0].audit)
        self.assertIsNone(list_publication_assets(publications, "pub-missing"))
        self.assertEqual(len(logger.events), 1)
        assert attached.publication_asset_id is not None
        missing = remove_publication_asset(
            publications,
            "pub-d8a-other",
            attached.publication_asset_id,
            _ACTOR,
            logger,
            request_id="req-d8a",
        )
        self.assertEqual(missing.result, "not_found")
        self.assertEqual(len(logger.events), 1)
        removed = remove_publication_asset(
            publications,
            "pub-d8a-audit",
            attached.publication_asset_id,
            _ACTOR,
            logger,
            request_id="req-d8a",
        )
        self.assertEqual(removed.result, "removed")
        self.assertEqual([event.action for event in logger.events], ["publication_asset_attached", "publication_asset_removed"])
        removed_detail = json.loads(logger.events[1].detail)
        self.assertEqual(
            removed_detail,
            {
                "publication_id": "pub-d8a-audit",
                "publication_asset_id": attached.publication_asset_id,
                "file_id": _FILE,
                "kind": "image",
                "checksum": "checksum-audit",
            },
        )


class _Capture:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


_POOL: object | None = None


def _pool() -> object:
    global _POOL
    if _POOL is not None:
        return _POOL
    from psycopg_pool import ConnectionPool

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import migrate

    dsn = os.environ["K12_PG_DSN"]
    applied = migrate(dsn, repo_root(), "up")
    if "V008" not in applied and "V008" not in _versions(dsn):
        raise RuntimeError("V008 was not applied")
    _POOL = ConnectionPool(dsn, min_size=1, max_size=2, open=True)
    return _POOL


def _versions(dsn: str) -> set[str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row[0]) for row in rows}


def _execute(pool: object, statement: str, params: tuple[object, ...] = ()) -> None:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            conn.execute(statement, params)


def _opposed_checksums(publication_id: str) -> tuple[str, str]:
    ranked = sorted(
        (asset_id_for(publication_id, f"checksum-order-{index:02d}"), f"checksum-order-{index:02d}")
        for index in range(32)
    )
    return ranked[-1][1], ranked[0][1]
