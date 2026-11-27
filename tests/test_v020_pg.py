"""V020 and intake archive on the scratch database. Skipped unless K12_PG_DSN is set.

The archive run only marks rows this test created. It does not call the command against the shared database.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err, Ok

OLD = "2026-10-01T00:00:00Z"
PHRASE = "synth-passphrase-r10"
BAIT_STUDENT = "student-r10-bait"
BAIT_EXT = "synth-ext-r10-bait"
BAIT_STEM = "synth-stem-bait-r10"
BAIT_TRANSCRIPT = "synth-transcript-bait-r10"
BAIT_COMMENT = "synth-comment-bait-r10"
BAITS = (BAIT_STUDENT, BAIT_EXT, BAIT_STEM, BAIT_TRANSCRIPT, BAIT_COMMENT, PHRASE)


class _Log:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class _Only:
    """Expose only this test's intake rows. Other scratch rows stay untouched."""

    def __init__(self, inner: object, allowed: set[str]) -> None:
        self._inner = inner
        self._allowed = allowed

    def unarchived(self) -> tuple[object, ...]:
        return tuple(row for row in self._inner.unarchived() if row.intake_id in self._allowed)  # type: ignore[attr-defined]

    def mark_archived(self, intake_ids: tuple[str, ...], archived_at: str) -> None:
        extra = set(intake_ids) - self._allowed
        if extra:
            raise AssertionError("archive tried to mark rows outside the test")
        self._inner.mark_archived(tuple(intake_ids), archived_at)  # type: ignore[attr-defined]

    def count_open_file(self, file_id: str) -> int:
        return int(self._inner.count_open_file(file_id))  # type: ignore[attr-defined]

    def get(self, intake_id: str) -> object:
        return self._inner.get(intake_id)  # type: ignore[attr-defined]


class IntakeArchivePgTest(unittest.TestCase):
    def setUp(self) -> None:
        dsn = os.environ.get("K12_PG_DSN", "").strip()
        if not dsn:
            self.skipTest("K12_PG_DSN is not set")
        from scripts.trial_bundle import database_name, is_dev_database

        try:
            name = database_name(dsn)
        except Exception as exc:
            self.fail(type(exc).__name__)
        if is_dev_database(name):
            self.fail("refusing database k12")
        from psycopg_pool import ConnectionPool

        from backend.bootstrap.compose import repo_root
        from backend.bootstrap.migrate import migrate
        from backend.practice.adapters.pg_decision import PgDecisions
        from backend.practice.adapters.pg_files import PgFiles
        from backend.practice.adapters.pg_intake import PgIntake
        from backend.practice.adapters.pg_items import PgPracticeItems
        from backend.practice.adapters.pg_practice import PgPractice

        self.dsn = dsn
        migrate(dsn, repo_root(), "up")
        self.pool = ConnectionPool(dsn, min_size=1, max_size=1, open=True)
        self.directory = tempfile.TemporaryDirectory()
        self.files = PgFiles(self.pool, Path(self.directory.name))
        self.intake = PgIntake(self.pool)
        self.practice = PgPractice(self.pool)
        self.items = PgPracticeItems(self.pool)
        self.decisions = PgDecisions(self.pool)
        self.papers: list[str] = []
        self.file_ids: list[str] = []
        self.logger = _Log()

    def tearDown(self) -> None:
        pool = getattr(self, "pool", None)
        if pool is not None:
            self._cleanup()
            pool.close()
        directory = getattr(self, "directory", None)
        if directory is not None:
            directory.cleanup()

    def test_v020_up_down_up(self) -> None:
        self.pool.close()
        self.pool = None
        _v020_round_trip(self.dsn)

    def test_pg_archives_only_expired_intake_and_keeps_history(self) -> None:
        from backend.ai.adapters.pg_runs import PgRuns
        from backend.ai.domain.records import Run, Suggestion
        from backend.practice.application.archive_intake import run_archive
        from backend.practice.domain.decision import TeacherDecision
        from scripts.archive_intake import _open, _seal

        done = self._issue("paper-r10-done")
        opened = self._issue("paper-r10-open")
        fresh = self._issue("paper-r10-fresh")
        pdf_paper = self._issue("paper-r10-pdf")
        old = self._upload(done, b"R10-OLD")
        current = self._upload(done, b"R10-NEW", replace=True)
        untouched = self._upload(opened, b"R10-OPEN")
        recent = self._upload(fresh, b"R10-FRESH")
        self._stamp(old["intake_id"], superseded=OLD)
        self._stamp(untouched["intake_id"], uploaded=OLD)
        self.decisions.replace(_decision("d-r10-done", done, OLD))
        self.decisions.replace(_decision("d-r10-fresh", fresh, _now()))
        self.decisions.replace(_decision("d-r10-pdf", pdf_paper, OLD))
        pdf_id, _pdf_sum = self.files.add(b"%PDF-synth-r10")
        self.file_ids.append(pdf_id)
        pdf_intake = "intake-r10-pdf"
        self._insert_page(pdf_intake, pdf_paper, pdf_id)
        runs = PgRuns(self.pool)
        runs.insert(
            Run(
                run_id="run-r10-pg",
                intake_id=str(current["intake_id"]),
                provider="mock",
                model="mock",
                prompt_version="synth-v1",
                status="queued",
                started_at=OLD,
            )
        )
        runs.finish(
            "run-r10-pg",
            status="succeeded",
            error_code="",
            input_tokens=1,
            output_tokens=1,
            external_match="unread",
            page_match="unread",
            suggestions=(
                Suggestion(
                    run_id="run-r10-pg",
                    paper_id=done,
                    order_no=1,
                    transcription=BAIT_TRANSCRIPT,
                    unreadable=False,
                    confidence=0.9,
                    verdict="correct",
                    reason="synth",
                    judged_by="local",
                ),
            ),
        )
        allowed = {
            str(old["intake_id"]),
            str(current["intake_id"]),
            str(untouched["intake_id"]),
            str(recent["intake_id"]),
            pdf_intake,
        }
        limited = _Only(self.intake, allowed)
        now = datetime.now(timezone.utc)
        out = Path(self.directory.name) / "archives"
        before = self._archived_ids()
        dry = run_archive(
            limited,
            self.items,
            self.decisions,
            self.files,
            cutoff=now - timedelta(days=30),
            now=now,
            retention_days=30,
            out_dir=out,
            encrypt=True,
            dry_run=True,
            logger=self.logger,
            seal=_seal,
            opener=_open,
        )
        self.assertEqual((dry.confirmed, dry.superseded, dry.archived), (1, 1, 0))
        self.assertGreater(dry.total_bytes, 0)
        self.assertFalse(out.exists())
        self.assertEqual(self._archived_ids(), before)
        saved = {
            "old": self.files.read(str(old["file_id"])),
            "current": self.files.read(str(current["file_id"])),
            "open": self.files.read(str(untouched["file_id"])),
            "fresh": self.files.read(str(recent["file_id"])),
            "pdf": self.files.read(pdf_id),
        }
        self.assertIsNotNone(saved["pdf"])
        with mock.patch.dict(os.environ, {"K12_BACKUP_PASSPHRASE": PHRASE}):
            report = run_archive(
                limited,
                self.items,
                self.decisions,
                self.files,
                cutoff=now - timedelta(days=30),
                now=now,
                retention_days=30,
                out_dir=out,
                encrypt=True,
                dry_run=False,
                logger=self.logger,
                seal=_seal,
                opener=_open,
            )
            self.assertEqual(report.code, 0, report)
            archive = report.archive
            self.assertIsNotNone(archive)
            assert archive is not None
            self.assertTrue(archive.name.endswith(".tar.gz.enc"))
            self.assertEqual([path.name for path in out.iterdir()], [archive.name])
            self.assertFalse(archive.read_bytes().startswith(b"\x1f\x8b"))
            from scripts.trial_bundle import openssl_convert

            text = _manifest_text(archive, openssl_convert)
        for hidden in BAITS:
            self.assertNotIn(hidden, text)
        document = json.loads(text)
        self.assertEqual(
            sorted((row["intake_id"], row["reason"]) for row in document["items"]),
            sorted(((str(current["intake_id"]), "confirmed"), (str(old["intake_id"]), "superseded"))),
        )
        self.assertIsNone(self.files.read(str(old["file_id"])))
        self.assertIsNone(self.files.read(str(current["file_id"])))
        self.assertEqual(self.files.read(str(untouched["file_id"])), saved["open"])
        self.assertEqual(self.files.read(str(recent["file_id"])), saved["fresh"])
        self.assertEqual(self.files.read(pdf_id), saved["pdf"])
        self.assertEqual(self._purpose(pdf_id), "page")
        self.assertEqual(self._purpose(str(current["file_id"])), "intake")
        self.assertIsNotNone(self.intake.get(str(current["intake_id"])).archived_at)  # type: ignore[union-attr]
        self.assertIsNotNone(self.intake.get(str(old["intake_id"])).archived_at)  # type: ignore[union-attr]
        self.assertIsNone(self.intake.get(str(untouched["intake_id"])).archived_at)  # type: ignore[union-attr]
        self.assertIsNone(self.intake.get(pdf_intake).archived_at)  # type: ignore[union-attr]
        self.assertEqual(self._count("teacher_decision", done), 1)
        self.assertEqual(self._count("ai_suggestion", done), 1)
        self.assertEqual(self._transcript("run-r10-pg"), BAIT_TRANSCRIPT)
        self.assertEqual(self._archived_ids() - before, {str(current["intake_id"]), str(old["intake_id"])})
        detail = json.loads(self.logger.events[-1].detail)
        self.assertEqual(set(detail), {"eligible", "archived", "deleted_files", "retention_days"})
        self.assertEqual(detail["deleted_files"], 2)
        for hidden in BAITS:
            self.assertNotIn(hidden, self.logger.events[-1].detail)
        again = run_archive(
            limited,
            self.items,
            self.decisions,
            self.files,
            cutoff=now - timedelta(days=30),
            now=now,
            retention_days=30,
            out_dir=out,
            encrypt=True,
            dry_run=False,
            logger=self.logger,
            seal=_seal,
            opener=_open,
        )
        self.assertEqual((again.eligible, again.archived), (0, 0))
        self.assertEqual(len(list(out.iterdir())), 1)
        self.assertFalse(self.files.delete_online_bytes(pdf_id))
        self.assertEqual(self.files.read(pdf_id), saved["pdf"])

    def test_checksum_mismatch_marks_nothing(self) -> None:
        from backend.practice.application.archive_intake import run_archive
        from backend.practice.domain.decision import TeacherDecision

        paper_id = self._issue("paper-r10-bad")
        uploaded = self._upload(paper_id, b"R10-BAD")
        self.decisions.replace(_decision("d-r10-bad", paper_id, OLD))
        path = Path(self.directory.name) / str(uploaded["file_id"])
        path.write_bytes(b"synth-r10-tamper")
        limited = _Only(self.intake, {str(uploaded["intake_id"])})
        now = datetime.now(timezone.utc)
        out = Path(self.directory.name) / "bad-archives"

        def seal(*_args: object) -> Path:
            raise AssertionError("sealed a mismatched archive")

        report = run_archive(
            limited,
            self.items,
            self.decisions,
            self.files,
            cutoff=now - timedelta(days=30),
            now=now,
            retention_days=30,
            out_dir=out,
            encrypt=False,
            dry_run=False,
            logger=self.logger,
            seal=seal,  # type: ignore[arg-type]
            opener=lambda _path, _encrypt: True,
        )
        self.assertEqual(report.code, 1)
        self.assertIsNone(self.intake.get(str(uploaded["intake_id"])).archived_at)  # type: ignore[union-attr]
        self.assertTrue(path.is_file())
        self.assertEqual(self._count("teacher_decision", paper_id), 1)

    def _issue(self, paper_id: str) -> str:
        from backend.practice.domain.item import PracticeItem
        from backend.practice.domain.paper import freeze_paper

        frozen = freeze_paper(
            paper_id=paper_id,
            teacher_id="teacher-r10-pg",
            student_id=BAIT_STUDENT,
            subject_id="math",
            question_version_id="qv-r10-pg",
            answer_version_id="av-r10-pg",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-r10-pg",
            item_order=("sq-1",),
            printed_external_id=BAIT_EXT,
            issued_on="2026-10-01",
        )
        self.assertNotIsInstance(frozen, Err)
        assert not isinstance(frozen, Err)
        self.papers.append(paper_id)
        self.items.place_composed(
            frozen,
            (
                PracticeItem(
                    paper_id=paper_id,
                    order_no=1,
                    question_version_id="qv-r10-pg",
                    answer_version_id="av-r10-pg",
                    stem_text=BAIT_STEM,
                    answer_text="synth-answer",
                    page_no=1,
                ),
            ),
        )
        return paper_id

    def _upload(self, paper_id: str, extra: bytes, *, replace: bool = False) -> dict[str, object]:
        from backend.practice.application.intake_photo import upload_intake

        result = upload_intake(
            paper_id=paper_id,
            page_no=1,
            body=_jpeg(extra),
            content_type="image/jpeg",
            located_by="manual",
            qr_text="",
            replace=replace,
            actor_id="teacher-r10-pg",
            actor_role="teacher",
            practice=self.practice,
            items=self.items,
            files=self.files,
            intake=self.intake,
            logger=self.logger,
            request_id="req-r10-pg",
        )
        self.assertIsInstance(result, Ok, result)
        assert isinstance(result, Ok)
        self.file_ids.append(str(result.value["file_id"]))
        return result.value

    def _stamp(self, intake_id: str, *, superseded: str = "", uploaded: str = "") -> None:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                if superseded:
                    conn.execute(
                        "UPDATE intake_page SET superseded_at = %s WHERE intake_id = %s",
                        (superseded, intake_id),
                    )
                if uploaded:
                    conn.execute(
                        "UPDATE intake_page SET uploaded_at = %s WHERE intake_id = %s",
                        (uploaded, intake_id),
                    )

    def _insert_page(self, intake_id: str, paper_id: str, file_id: str) -> None:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO intake_page (
                        intake_id, paper_id, page_no, file_id, uploaded_by, uploaded_at, located_by
                    ) VALUES (%s, %s, 1, %s, 'teacher-r10-pg', %s, 'manual')
                    """,
                    (intake_id, paper_id, file_id, OLD),
                )

    def _archived_ids(self) -> set[str]:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(
                "SELECT intake_id FROM intake_page WHERE archived_at IS NOT NULL AND paper_id = ANY(%s)",
                (self.papers,),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def _purpose(self, file_id: str) -> str:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT purpose FROM files WHERE file_id = %s", (file_id,)).fetchone()
        return "" if row is None else str(row[0])

    def _count(self, table: str, paper_id: str) -> int:
        if table not in {"teacher_decision", "ai_suggestion"}:
            raise AssertionError(table)
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                f"SELECT count(*) FROM {table} WHERE paper_id = %s",  # noqa: S608
                (paper_id,),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def _transcript(self, run_id: str) -> str:
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT transcription FROM ai_suggestion WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return "" if row is None else str(row[0])

    def _cleanup(self) -> None:
        papers = list(self.papers)
        if not papers and not self.file_ids:
            return
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            with conn.transaction():
                linked: list[str] = []
                if papers:
                    conn.execute("DELETE FROM ai_suggestion WHERE paper_id = ANY(%s)", (papers,))
                    conn.execute(
                        """
                        DELETE FROM ai_run
                        WHERE intake_id IN (SELECT intake_id FROM intake_page WHERE paper_id = ANY(%s))
                        """,
                        (papers,),
                    )
                    conn.execute("DELETE FROM teacher_decision WHERE paper_id = ANY(%s)", (papers,))
                    linked = [
                        str(row[0])
                        for row in conn.execute(
                            "SELECT file_id FROM intake_page WHERE paper_id = ANY(%s)",
                            (papers,),
                        ).fetchall()
                    ]
                    for statement in (
                        "DELETE FROM intake_page WHERE paper_id = ANY(%s)",
                        "DELETE FROM practice_item_box WHERE paper_id = ANY(%s)",
                        "DELETE FROM practice_item WHERE paper_id = ANY(%s)",
                        "DELETE FROM paper_pages WHERE paper_id = ANY(%s)",
                        "DELETE FROM attempts WHERE paper_id = ANY(%s)",
                        "DELETE FROM confirmations WHERE paper_id = ANY(%s)",
                        "DELETE FROM papers WHERE paper_id = ANY(%s)",
                    ):
                        conn.execute(statement, (papers,))
                file_ids = list(dict.fromkeys([*self.file_ids, *linked]))
                if file_ids:
                    conn.execute("DELETE FROM files WHERE file_id = ANY(%s)", (file_ids,))


def _decision(decision_id: str, paper_id: str, decided_at: str) -> object:
    from backend.practice.domain.decision import TeacherDecision

    return TeacherDecision(
        decision_id=decision_id,
        paper_id=paper_id,
        order_no=1,
        verdict="correct",
        source="manual",
        decided_by="teacher-r10-pg",
        decided_at=decided_at,
        comment=BAIT_COMMENT,
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jpeg(extra: bytes) -> bytes:
    payload = b"synth-r10" + extra
    length = len(payload) + 2
    segment = bytes((0xFF, 0xDA, (length >> 8) & 0xFF, length & 0xFF)) + payload
    return b"\xff\xd8" + segment + b"\xff\xd9"


def _manifest_text(path: Path, openssl_convert: object) -> str:
    import tarfile

    with tempfile.TemporaryDirectory(prefix="k12-r10-pg-read-") as raw:
        work = Path(raw)
        tar_path = work / "bundle.tar.gz"
        openssl_convert(path, tar_path, decrypt=True)  # type: ignore[operator]
        unpacked = work / "out"
        unpacked.mkdir()
        with tarfile.open(tar_path, "r:gz") as packed:
            packed.extractall(unpacked, filter="data")
        return (unpacked / "archive-manifest.json").read_text(encoding="utf-8")


def _v020_round_trip(dsn: str) -> None:
    from scripts.trial_bundle import database_name, is_dev_database

    if is_dev_database(database_name(dsn)):
        raise AssertionError("refusing database k12")
    import psycopg

    from backend.bootstrap.compose import repo_root
    from backend.bootstrap.migrate import discover, migrate, sql_statements

    root = repo_root()
    migrate(dsn, root, "up")
    item = next(row for row in discover(root) if row.version == "V020")
    _expect_v020(dsn, True)
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                for statement in sql_statements(item.down.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", ("V020",))
        _expect_v020(dsn, False)
    finally:
        migrate(dsn, root, "up")
        _expect_v020(dsn, True)


def _expect_v020(dsn: str, present: bool) -> None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        column = conn.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_name = 'intake_page' AND column_name = 'archived_at'
            """
        ).fetchone()
    if present:
        if column is None or column[0] != "YES":
            raise AssertionError("intake_page.archived_at is missing or not nullable")
        return
    if column is not None:
        raise AssertionError("intake_page.archived_at is still present")
