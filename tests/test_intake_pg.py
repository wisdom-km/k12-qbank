"""Intake rows on PostgreSQL. Skipped unless K12_PG_DSN names the scratch database."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok
from backend.practice.application.intake_photo import intake_status, upload_intake
from backend.practice.domain.intake_image import strip_jpeg_capture
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import freeze_paper
from backend.practice.domain.qr_code import qr_payload

MARKER = b"EXIF-MARKER-SYNTH"
APP13 = b"APP13-MARKER-SYNTH"
PIXELS = b"IMAGE-BYTES-SYNTH"
EXTERNAL = "synth-r5-ext"


class _Capture:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class IntakePgTest(unittest.TestCase):
    def setUp(self) -> None:
        if not os.environ.get("K12_PG_DSN", "").strip():
            self.skipTest("K12_PG_DSN is not set")
        from psycopg_pool import ConnectionPool

        from backend.bootstrap.compose import repo_root
        from backend.bootstrap.migrate import migrate
        from backend.practice.adapters.pg_files import PgFiles
        from backend.practice.adapters.pg_intake import PgIntake
        from backend.practice.adapters.pg_items import PgPracticeItems
        from backend.practice.adapters.pg_practice import PgPractice

        self.dsn = os.environ["K12_PG_DSN"]
        migrate(self.dsn, repo_root(), "up")
        self.pool = ConnectionPool(self.dsn, min_size=1, max_size=1, open=True)
        self.directory = tempfile.TemporaryDirectory()
        self.files = PgFiles(self.pool, Path(self.directory.name))
        self.intake = PgIntake(self.pool)
        self.practice = PgPractice(self.pool)
        self.items = PgPracticeItems(self.pool)
        self.logger = _Capture()
        self.papers: list[str] = []
        self.file_ids: list[str] = []

    def tearDown(self) -> None:
        pool = getattr(self, "pool", None)
        if pool is not None:
            self._cleanup()
            pool.close()
        directory = getattr(self, "directory", None)
        if directory is not None:
            directory.cleanup()

    def test_pg_upload_strips_jpeg_replaces_and_keeps_one_current(self) -> None:
        paper_id = self._issue("paper-r5-pg-keep")
        first = self._upload(paper_id, 1, _jpeg(), located_by="qr", qr_text=qr_payload(paper_id, 1))
        self.assertIsInstance(first, Ok)
        assert isinstance(first, Ok)
        stored = self.files.read(str(first.value["file_id"]))
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertNotIn(MARKER, stored)
        self.assertNotIn(APP13, stored)
        self.assertIn(PIXELS, stored)
        self.assertTrue(stored.startswith(b"\xff\xd8"))
        status = intake_status(
            paper_id=paper_id,
            actor_id="teacher-r5-pg",
            actor_role="teacher",
            practice=self.practice,
            items=self.items,
            intake=self.intake,
            logger=self.logger,
            request_id="req-r5-status",
        )
        self.assertIsInstance(status, Ok)
        assert isinstance(status, Ok)
        self.assertTrue(status.value["pages"][0]["received"])  # type: ignore[index]
        again = self._upload(paper_id, 1, _jpeg(extra=b"SECOND"), located_by="manual")
        self.assertIsInstance(again, Err)
        assert isinstance(again, Err)
        self.assertEqual(again.code, "page_already_received")
        replaced = self._upload(paper_id, 1, _jpeg(extra=b"SECOND"), located_by="manual", replace=True)
        self.assertIsInstance(replaced, Ok)
        assert isinstance(replaced, Ok)
        self.assertTrue(replaced.value["replaced"])
        old = self.intake.get(str(first.value["intake_id"]))
        current = self.intake.current(paper_id, 1)
        self.assertIsNotNone(old)
        assert old is not None and current is not None
        self.assertIsNotNone(old.superseded_at)
        self.assertIsNone(current.superseded_at)
        self.assertEqual(current.intake_id, replaced.value["intake_id"])
        self.assertEqual(len(self.intake.currents(paper_id)), 1)
        self.assertEqual(self._row_count(paper_id), 2)
        self.assertIsNotNone(self.files.read(old.file_id))
        text = "\n".join(event.detail for event in self.logger.events)
        self.assertNotIn(EXTERNAL, text)
        self.assertNotIn(PIXELS.decode("ascii"), text)
        self.assertNotIn(MARKER.decode("ascii"), text)

    def test_pg_bad_inputs_and_a_page_file_write_no_intake_row(self) -> None:
        paper_id = self._issue("paper-r5-pg-none")
        before = self._row_count(paper_id)
        cases = [
            self._upload(paper_id, 9, _jpeg(), located_by="manual"),
            self._upload("missing-paper-r5", 1, _jpeg(), located_by="manual"),
            self._upload(paper_id, 1, _jpeg(), located_by="qr", qr_text="not-this-paper#1"),
            self._upload(paper_id, 1, b"not-an-image", located_by="manual"),
        ]
        self.assertEqual([item.code for item in cases if isinstance(item, Err)], [
            "page_out_of_range",
            "paper_not_found",
            "qr_mismatch",
            "not_image",
        ])
        self.assertTrue(all(isinstance(item, Err) for item in cases))
        with unittest.mock.patch.dict(os.environ, {"K12_INTAKE_MAX_BYTES": "32"}):
            huge = self._upload(paper_id, 1, _jpeg(), located_by="manual")
        self.assertIsInstance(huge, Err)
        assert isinstance(huge, Err)
        self.assertEqual(huge.code, "too_large")
        stored = strip_jpeg_capture(_jpeg(extra=b"PAGE"))
        digest = hashlib.sha256(stored).hexdigest()
        file_id = "file-" + digest[:16]
        self.file_ids.append(file_id)
        self._insert_page_file(file_id, digest)
        conflict = self._upload(paper_id, 1, _jpeg(extra=b"PAGE"), located_by="manual")
        self.assertIsInstance(conflict, Err)
        assert isinstance(conflict, Err)
        self.assertEqual(conflict.code, "file_purpose_conflict")
        self.assertEqual(self._row_count(paper_id), before)
        self.assertEqual(self._purpose(file_id), "page")
        text = "\n".join(event.detail for event in self.logger.events)
        self.assertNotIn(EXTERNAL, text)

    def test_v014_down_then_up(self) -> None:
        self.pool.close()
        self.pool = None
        _v014_round_trip(self.dsn)

    def _issue(self, paper_id: str) -> str:
        frozen = freeze_paper(
            paper_id=paper_id,
            teacher_id="teacher-r5-pg",
            student_id="student-r5-pg",
            subject_id="math",
            question_version_id="qv-r5-pg",
            answer_version_id="av-r5-pg",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-r5-pg",
            item_order=("sq-1",),
            printed_external_id=EXTERNAL,
            issued_on="2026-11-24",
        )
        self.assertNotIsInstance(frozen, Err)
        assert not isinstance(frozen, Err)
        self.papers.append(paper_id)
        self._cleanup()
        item = PracticeItem(
            paper_id=paper_id,
            order_no=1,
            question_version_id="qv-r5-pg",
            answer_version_id="av-r5-pg",
            stem_text="synth-stem",
            answer_text="synth-hidden",
            page_no=1,
        )
        self.items.place_composed(frozen, (item,))
        loaded = self.practice.get_paper(paper_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.issued_on, "2026-11-24")
        self.assertEqual(loaded.printed_external_id, EXTERNAL)
        return paper_id

    def _upload(
        self,
        paper_id: str,
        page_no: int,
        body: bytes,
        *,
        located_by: str,
        qr_text: str = "",
        replace: bool = False,
    ) -> Ok[dict[str, object]] | Err:
        result = upload_intake(
            paper_id=paper_id,
            page_no=page_no,
            body=body,
            content_type="image/jpeg",
            located_by=located_by,
            qr_text=qr_text,
            replace=replace,
            actor_id="teacher-r5-pg",
            actor_role="teacher",
            practice=self.practice,
            items=self.items,
            files=self.files,
            intake=self.intake,
            logger=self.logger,
            request_id="req-r5-pg",
        )
        if isinstance(result, Ok):
            self.file_ids.append(str(result.value["file_id"]))
        return result

    def _row_count(self, paper_id: str) -> int:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT count(*) FROM intake_page WHERE paper_id = %s",
                (paper_id,),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def _purpose(self, file_id: str) -> str:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT purpose FROM files WHERE file_id = %s", (file_id,)).fetchone()
        return "" if row is None else str(row[0])

    def _insert_page_file(self, file_id: str, checksum: str) -> None:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                conn.execute(
                    "INSERT INTO files (file_id, purpose, checksum) VALUES (%s, 'page', %s)",
                    (file_id, checksum),
                )

    def _cleanup(self) -> None:
        papers = tuple(self.papers)
        file_ids = tuple(dict.fromkeys(self.file_ids))
        if not papers and not file_ids:
            return
        statements = (
            "DELETE FROM intake_page WHERE paper_id = ANY(%s)",
            "DELETE FROM practice_item_box WHERE paper_id = ANY(%s)",
            "DELETE FROM practice_item WHERE paper_id = ANY(%s)",
            "DELETE FROM paper_pages WHERE paper_id = ANY(%s)",
            "DELETE FROM attempts WHERE paper_id = ANY(%s)",
            "DELETE FROM confirmations WHERE paper_id = ANY(%s)",
            "DELETE FROM papers WHERE paper_id = ANY(%s)",
        )
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                for statement in statements:
                    if papers:
                        conn.execute(statement, (list(papers),))
                if file_ids:
                    conn.execute("DELETE FROM files WHERE file_id = ANY(%s)", (list(file_ids),))


def _jpeg(extra: bytes = b"") -> bytes:
    def segment(marker: int, payload: bytes) -> bytes:
        length = len(payload) + 2
        return bytes((0xFF, marker, (length >> 8) & 0xFF, length & 0xFF)) + payload

    return b"\xff\xd8" + segment(0xE1, MARKER) + segment(0xED, APP13) + segment(0xDA, b"") + PIXELS + extra + b"\xff\xd9"


def _v014_round_trip(dsn: str) -> None:
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    found = discover(root)
    item = next(row for row in found if row.version == "V014")
    # Later migrations can reference intake_page. Peel them before V014's own down.
    later = [row for row in found if row.version > "V014"]
    _expect_v014(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for row in reversed(later):
                    for statement in sql_statements(row.down.read_text(encoding="utf-8")):
                        conn.execute(statement)
                    conn.execute(
                        "DELETE FROM schema_migrations WHERE version = %s",
                        (row.version,),
                    )
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V014",))
        _expect_v014(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v014(dsn, True)


def _expect_v014(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        table = conn.execute("SELECT to_regclass('public.intake_page')").fetchone()
        column = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'papers' AND column_name = 'issued_on'
            """
        ).fetchone()
        constraint = conn.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'files_purpose_known'"
        ).fetchone()
    found = table is not None and table[0] is not None and column is not None and constraint is not None
    if present and not found:
        raise AssertionError("V014 objects missing")
    if not present and (table is not None and table[0] is not None or column is not None or constraint is not None):
        raise AssertionError("V014 objects still present")
