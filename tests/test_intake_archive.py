"""Intake photos archive only after the whole paper is confirmed, or after a replacement ages out.

Fixtures are synthetic. The archive manifest and the log carry counts and ids, not stems or a passphrase.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.ai.adapters.memory_runs import MemoryRuns
from backend.ai.application.load import load_context
from backend.ai.application.recognize import start_run
from backend.ai.domain.records import Run, Suggestion
from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_ADMIN_ID, ACTOR_TEACHER_ID, SYNTH_SECRET
from backend.identity.domain.records import Grant, Student
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err
from backend.practice.adapters.files import MemoryFiles
from backend.practice.adapters.memory_decision import MemoryDecisions
from backend.practice.adapters.memory_intake import MemoryIntake
from backend.practice.adapters.memory_items import MemoryPracticeItems
from backend.practice.application.archive_intake import (
    ArchiveItem,
    ArchiveReport,
    PageView,
    PaperClock,
    plan,
    run_archive,
    select_eligible,
)
from backend.practice.application.intake_photo import read_intake_image
from backend.practice.domain.decision import TeacherDecision
from backend.practice.domain.intake_page import IntakePage
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.paper import freeze_paper
from scripts.archive_intake import ROOT, main
from scripts.trial_bundle import openssl_convert

NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=30)
OLD = "2026-10-01T00:00:00Z"
RECENT = "2026-11-26T00:00:00Z"
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


class EligibilityTest(unittest.TestCase):
    def test_confirmed_old_is_eligible_and_unfinished_or_recent_is_not(self) -> None:
        pages = (
            _page("in-done", "paper-done", superseded=None),
            _page("in-open", "paper-open", superseded=None),
            _page("in-fresh", "paper-fresh", superseded=None),
            _page("in-empty", "paper-empty", superseded=None),
            _page("in-pdf", "paper-pdf", superseded=None, purpose="page"),
            _page("in-old", "paper-replaced", superseded=OLD),
            _page("in-new", "paper-replaced", superseded=RECENT),
            _page("in-kept", "paper-done", superseded=None, archived=OLD),
        )
        clocks = {
            "paper-done": PaperClock(1, 1, _at(OLD)),
            "paper-open": PaperClock(2, 1, _at(OLD)),
            "paper-fresh": PaperClock(1, 1, _at(RECENT)),
            "paper-empty": PaperClock(0, 0, _at(OLD)),
            "paper-pdf": PaperClock(1, 1, _at(OLD)),
            "paper-replaced": PaperClock(1, 0, None),
        }
        chosen = select_eligible(pages, clocks, CUTOFF)
        self.assertEqual([(row.intake_id, row.reason) for row in chosen], [("in-done", "confirmed"), ("in-old", "superseded")])

    def test_equal_cutoff_is_eligible_and_one_second_later_is_not(self) -> None:
        on_time = _page("in-on", "paper-on", superseded=None)
        late = _page("in-late", "paper-late", superseded=None)
        clocks = {
            "paper-on": PaperClock(1, 1, CUTOFF),
            "paper-late": PaperClock(1, 1, CUTOFF + timedelta(seconds=1)),
        }
        chosen = select_eligible((on_time, late), clocks, CUTOFF)
        self.assertEqual([row.intake_id for row in chosen], ["in-on"])

    def test_a_voided_decision_does_not_count(self) -> None:
        intake = MemoryIntake()
        items = MemoryPracticeItems()
        decisions = MemoryDecisions()
        files = MemoryFiles()
        _store(intake, files, "in-1", "paper-1", b"synth-photo-r10-void", superseded=None)
        items.set_items("paper-1", (_item("paper-1", 1),))
        decisions.replace(_decision("d-old", "paper-1", OLD))
        decisions.replace(_decision("d-new", "paper-1", RECENT))
        chosen = plan(intake, items, decisions, files, CUTOFF)
        self.assertEqual(chosen, ())

    def test_store_plan_matches_the_confirmed_and_superseded_rules(self) -> None:
        intake = MemoryIntake()
        items = MemoryPracticeItems()
        decisions = MemoryDecisions()
        files = MemoryFiles()
        _store(intake, files, "in-old", "paper-done", b"synth-photo-r10-old", superseded=OLD)
        _store(intake, files, "in-done", "paper-done", b"synth-photo-r10-done", superseded=None)
        _store(intake, files, "in-open", "paper-open", b"synth-photo-r10-open", superseded=None)
        pdf_id, _pdf_sum = files.add(b"%PDF-synth-r10")
        _store(intake, files, "in-pdf", "paper-pdf", b"%PDF-synth-r10", superseded=None, file_id=pdf_id, purpose_page=True)
        items.set_items("paper-done", (_item("paper-done", 1, BAIT_STEM),))
        items.set_items("paper-open", (_item("paper-open", 1), _item("paper-open", 2)))
        decisions.replace(_decision("d-done", "paper-done", OLD, comment=BAIT_COMMENT))
        chosen = plan(intake, items, decisions, files, CUTOFF)
        self.assertEqual([(row.intake_id, row.reason) for row in chosen], [("in-done", "confirmed"), ("in-old", "superseded")])
        self.assertEqual(files.read(pdf_id), b"%PDF-synth-r10")


class ArchiveRunTest(unittest.TestCase):
    def test_dry_run_counts_bytes_and_writes_nothing(self) -> None:
        world = _world(self)
        out = world.out
        report = _run(world, dry_run=True, encrypt=True)
        self.assertEqual(report.code, 0)
        self.assertEqual(report.confirmed, 1)
        self.assertEqual(report.superseded, 1)
        self.assertEqual(report.archived, 0)
        self.assertEqual(report.total_bytes, len(world.done) + len(world.old))
        self.assertIsNone(world.intake.get("in-done").archived_at)  # type: ignore[union-attr]
        self.assertEqual(world.files.read(world.done_id), world.done)
        self.assertEqual(list(out.iterdir()), [])
        self.assertEqual(world.log.events, [])

    def test_encrypted_archive_verifies_then_deletes_only_intake_bytes(self) -> None:
        world = _world(self)
        runs = MemoryRuns()
        runs.insert(
            Run(
                run_id="run-r10",
                intake_id="in-done",
                provider="mock",
                model="mock",
                prompt_version="synth-v1",
                status="succeeded",
                started_at=OLD,
                finished_at=OLD,
                suggestions=(
                    Suggestion(
                        run_id="run-r10",
                        paper_id="paper-done",
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
        )
        with mock.patch.dict(os.environ, {"K12_BACKUP_PASSPHRASE": PHRASE, "K12_PG_DSN": ""}):
            report = _run(world, dry_run=False, encrypt=True, real=True)
            self.assertEqual(report.code, 0, report)
            self.assertEqual(report.archived, 2)
            self.assertEqual(report.deleted, 2)
            archive = report.archive
            self.assertIsNotNone(archive)
            assert archive is not None
            self.assertTrue(archive.name.endswith(".tar.gz.enc"))
            self.assertFalse(archive.read_bytes().startswith(b"\x1f\x8b"))
            self.assertEqual([path.name for path in world.out.iterdir()], [archive.name])
            manifest_text = _manifest_text(archive)
            for hidden in BAITS:
                self.assertNotIn(hidden, manifest_text)
            document = json.loads(manifest_text)
            self.assertEqual(document["schema_version"], 1)
            self.assertEqual(document["retention_days"], 30)
            self.assertEqual(document["item_count"], 2)
            self.assertEqual(
                [(row["intake_id"], row["reason"]) for row in document["items"]],
                [("in-done", "confirmed"), ("in-old", "superseded")],
            )
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["--verify-archive", str(archive)])
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("ARCHIVE VERIFIED", out.getvalue())
        self.assertIsNone(world.files.read(world.done_id))
        self.assertIsNone(world.files.read(world.old_id))
        self.assertEqual(world.files.read(world.pdf_id), world.pdf)
        self.assertEqual(world.files.purpose(world.done_id), "intake")
        self.assertIsNotNone(world.intake.get("in-done").archived_at)  # type: ignore[union-attr]
        self.assertIsNotNone(world.intake.get("in-old").archived_at)  # type: ignore[union-attr]
        self.assertIsNone(world.intake.get("in-open").archived_at)  # type: ignore[union-attr]
        self.assertEqual(world.files.read(world.open_id), world.open)
        self.assertEqual(len(world.decisions.history("paper-done")), 1)
        stored = runs.get("run-r10")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.suggestions[0].transcription, BAIT_TRANSCRIPT)
        self.assertEqual(len(world.log.events), 1)
        event = world.log.events[0]
        self.assertEqual(event.event, "intake_archived")
        detail = json.loads(event.detail)
        self.assertEqual(set(detail), {"eligible", "archived", "deleted_files", "retention_days"})
        self.assertEqual(detail["archived"], 2)
        self.assertEqual(detail["deleted_files"], 2)
        text = event.detail + manifest_text
        for hidden in BAITS:
            self.assertNotIn(hidden, text)
        again = _run(world, dry_run=False, encrypt=True, real=True)
        self.assertEqual(again.eligible, 0)
        self.assertEqual(again.archived, 0)
        self.assertEqual(len(list(world.out.iterdir())), 1)

    def test_missing_passphrase_refuses_before_any_write(self) -> None:
        world = _world(self)
        env = {
            "K12_PG_DSN": "postgresql://k12:synth-pw@127.0.0.1:9/k12_trial",
            "K12_FILE_DIR": str(world.out),
            "K12_BACKUP_PASSPHRASE": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("scripts.archive_intake._run", side_effect=AssertionError("connected")):
                err = io.StringIO()
                with redirect_stderr(err):
                    code = main(["--out-dir", str(world.out / "archives")])
        self.assertEqual(code, 2)
        self.assertIn("K12_BACKUP_PASSPHRASE is required", err.getvalue())
        self.assertIsNone(world.intake.get("in-done").archived_at)  # type: ignore[union-attr]
        self.assertEqual(world.files.read(world.done_id), world.done)
        self.assertFalse((world.out / "archives").exists())

    def test_verify_failure_deletes_the_archive_and_leaves_the_database(self) -> None:
        world = _world(self)

        def seal(*_args: object) -> Path:
            path = world.out / "k12-intake-archive-broken.tar.gz.enc"
            path.write_bytes(b"synth-broken")
            return path

        report = run_archive(
            world.intake,
            world.items,
            world.decisions,
            world.files,
            cutoff=CUTOFF,
            now=NOW,
            retention_days=30,
            out_dir=world.out,
            encrypt=True,
            dry_run=False,
            logger=world.log,
            seal=seal,  # type: ignore[arg-type]
            opener=lambda _path, _encrypt: False,
        )
        self.assertEqual(report.code, 1)
        self.assertEqual(list(world.out.iterdir()), [])
        self.assertIsNone(world.intake.get("in-done").archived_at)  # type: ignore[union-attr]
        self.assertEqual(world.files.read(world.done_id), world.done)
        self.assertEqual(world.files.read(world.pdf_id), world.pdf)
        self.assertEqual(world.log.events, [])

    def test_checksum_mismatch_and_missing_bytes_write_nothing(self) -> None:
        world = _world(self)
        world.files.store_bytes(world.done_id, b"synth-photo-r10-tamper")
        report = _run(world, dry_run=False, encrypt=False, real=True)
        self.assertEqual(report.code, 1)
        self.assertEqual(list(world.out.glob("k12-intake-archive-*")), [])
        self.assertIsNone(world.intake.get("in-old").archived_at)  # type: ignore[union-attr]
        self.assertEqual(world.files.read(world.old_id), world.old)
        world.files.store_bytes(world.done_id, world.done)
        world.files.delete_online_bytes(world.done_id)
        missing = _run(world, dry_run=False, encrypt=False, real=True)
        self.assertEqual(missing.code, 1)
        self.assertIsNone(world.intake.get("in-old").archived_at)  # type: ignore[union-attr]
        self.assertEqual(world.files.read(world.old_id), world.old)

    def test_a_shared_file_stays_while_a_current_row_still_points_at_it(self) -> None:
        intake = MemoryIntake()
        items = MemoryPracticeItems()
        decisions = MemoryDecisions()
        files = MemoryFiles()
        data = b"synth-photo-r10-shared"
        digest = hashlib.sha256(data).hexdigest()
        file_id = "file-" + digest[:16]
        files.store_bytes(file_id, data)
        _place(intake, "in-old", "paper-share", file_id, digest, superseded=OLD)
        _place(intake, "in-now", "paper-share", file_id, digest, superseded=None)
        out = Path(tempfile.mkdtemp(prefix="k12-r10-share-"))
        self.addCleanup(lambda: _rm(out))
        report = run_archive(
            intake,
            items,
            decisions,
            files,
            cutoff=CUTOFF,
            now=NOW,
            retention_days=30,
            out_dir=out,
            encrypt=False,
            dry_run=False,
            logger=_Log(),
            seal=_marker,
            opener=lambda _path, _encrypt: True,
        )
        self.assertEqual(report.code, 0)
        self.assertEqual(report.superseded, 1)
        self.assertEqual(report.deleted, 0)
        self.assertEqual(files.read(file_id), data)
        self.assertIsNotNone(intake.get("in-old").archived_at)  # type: ignore[union-attr]
        self.assertIsNone(intake.get("in-now").archived_at)  # type: ignore[union-attr]

    def test_page_bytes_are_not_deleted_by_the_file_store(self) -> None:
        files = MemoryFiles()
        file_id, _digest = files.add(b"%PDF-synth-r10")
        self.assertFalse(files.delete_online_bytes(file_id))
        self.assertEqual(files.read(file_id), b"%PDF-synth-r10")
        intake_id = "file-" + hashlib.sha256(b"synth-photo-r10-gone").hexdigest()[:16]
        files.store_bytes(intake_id, b"synth-photo-r10-gone")
        self.assertTrue(files.delete_online_bytes(intake_id))
        self.assertIsNone(files.read(intake_id))
        self.assertTrue(files.delete_online_bytes(intake_id))
        self.assertEqual(files.purpose(intake_id), "intake")

    def test_nothing_eligible_prints_pass_and_skips_the_archive(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="k12-r10-empty-"))
        self.addCleanup(lambda: _rm(out))
        called = {"seal": 0}

        def seal(*_args: object) -> Path:
            called["seal"] += 1
            raise AssertionError("sealed an empty archive")

        report = run_archive(
            MemoryIntake(),
            MemoryPracticeItems(),
            MemoryDecisions(),
            MemoryFiles(),
            cutoff=CUTOFF,
            now=NOW,
            retention_days=30,
            out_dir=out,
            encrypt=True,
            dry_run=False,
            logger=_Log(),
            seal=seal,  # type: ignore[arg-type]
            opener=lambda _path, _encrypt: True,
        )
        self.assertEqual((report.code, report.eligible, report.archived, called["seal"]), (0, 0, 0, 0))
        self.assertEqual(list(out.iterdir()), [])

    def test_zero_eligible_command_prints_pass(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="k12-r10-cmd-"))
        self.addCleanup(lambda: _rm(directory))
        out = directory / "out"
        env = {
            "K12_PG_DSN": "postgresql://k12:synth-pw@127.0.0.1:9/k12_trial",
            "K12_FILE_DIR": str(directory),
            "K12_BACKUP_PASSPHRASE": PHRASE,
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch(
                "scripts.archive_intake._run",
                return_value=ArchiveReport(0, 0, 0, 0, 0, 0, 0),
            ) as runner:
                printed = io.StringIO()
                with redirect_stdout(printed):
                    code = main(["--out-dir", str(out)])
        self.assertEqual(code, 0)
        self.assertIn("ARCHIVE PASS eligible=0 archived=0", printed.getvalue())
        self.assertFalse(out.exists())
        self.assertEqual(runner.call_args.kwargs["encrypt"], True)

    def test_days_fall_back_to_thirty(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="k12-r10-days-"))
        self.addCleanup(lambda: _rm(directory))
        seen: dict[str, int] = {}

        def fake_run(*_args: object, **kwargs: object) -> ArchiveReport:
            seen["days"] = int(kwargs["days"])  # type: ignore[arg-type]
            return ArchiveReport(0, 0, 0, 0, 0, 0, 0)

        env = {
            "K12_PG_DSN": "postgresql://k12:synth-pw@127.0.0.1:9/k12_trial",
            "K12_FILE_DIR": str(directory),
            "K12_INTAKE_RETENTION_DAYS": "nope",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("scripts.archive_intake._run", side_effect=fake_run):
                with redirect_stdout(io.StringIO()):
                    code = main(["--dry-run", "--days", ""])
        self.assertEqual(code, 0)
        self.assertEqual(seen["days"], 30)


class CommandGuardTest(unittest.TestCase):
    def test_database_k12_and_unsafe_directories_are_refused(self) -> None:
        boom = mock.Mock(side_effect=AssertionError("connected"))
        cases = (
            ("postgresql://k12:synth-pw@127.0.0.1:9/k12", "", "database k12 is refused"),
            ("postgresql://k12:synth-pw@127.0.0.1:9/K12", "", "database k12 is refused"),
        )
        for dsn, _file_dir, expected in cases:
            with mock.patch.dict(os.environ, {"K12_PG_DSN": dsn, "K12_FILE_DIR": ""}, clear=False):
                with mock.patch("scripts.archive_intake._run", boom):
                    err = io.StringIO()
                    with redirect_stderr(err):
                        code = main(["--dry-run"])
            self.assertEqual(code, 2)
            self.assertIn(expected, err.getvalue())
        directory = Path(tempfile.mkdtemp(prefix="k12-r10-guard-"))
        self.addCleanup(lambda: _rm(directory))
        unsafe = directory / "repo"
        unsafe.mkdir()
        dotted = directory / "dotted"
        dotted.mkdir()
        (dotted / ".git").mkdir()
        missing = directory / "missing"
        env_base = {"K12_PG_DSN": "postgresql://k12:synth-pw@127.0.0.1:9/k12_trial"}
        checks = (
            ({**env_base, "K12_FILE_DIR": ""}, "K12_FILE_DIR is required"),
            ({**env_base, "K12_FILE_DIR": str(missing)}, "K12_FILE_DIR is not a directory"),
            ({**env_base, "K12_FILE_DIR": str(ROOT)}, "ARCHIVE REFUSED: unsafe file directory"),
            ({**env_base, "K12_FILE_DIR": str(directory)}, "ARCHIVE REFUSED: unsafe file directory"),
            ({**env_base, "K12_FILE_DIR": str(dotted)}, "ARCHIVE REFUSED: unsafe file directory"),
        )
        for env, expected in checks:
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("scripts.archive_intake.ROOT", unsafe):
                    with mock.patch("scripts.archive_intake._run", boom):
                        err = io.StringIO()
                        with redirect_stderr(err):
                            code = main(["--dry-run"])
            self.assertEqual(code, 2, expected)
            self.assertIn(expected, err.getvalue())
        boom.assert_not_called()

    def test_verify_requires_a_passphrase_for_an_encrypted_archive(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="k12-r10-verify-"))
        self.addCleanup(lambda: _rm(directory))
        archive = directory / "k12-intake-archive-synth.tar.gz.enc"
        archive.write_bytes(b"synth-cipher")
        with mock.patch.dict(
            os.environ,
            {"K12_PG_DSN": "", "K12_BACKUP_PASSPHRASE": ""},
            clear=False,
        ):
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["--verify-archive", str(archive)])
        self.assertEqual(code, 2)
        self.assertIn("K12_BACKUP_PASSPHRASE is required", err.getvalue())
        self.assertTrue(archive.is_file())
        with mock.patch.dict(
            os.environ,
            {"K12_PG_DSN": "postgresql://k12:synth-pw@127.0.0.1:9/k12", "K12_BACKUP_PASSPHRASE": PHRASE},
            clear=False,
        ):
            err = io.StringIO()
            with redirect_stderr(err):
                refused = main(["--verify-archive", str(archive)])
        self.assertEqual(refused, 2)
        self.assertIn("database k12 is refused", err.getvalue())

    def test_retention_sweep_leaves_intake_to_the_archive_command(self) -> None:
        text = (ROOT / "scripts" / "retention_sweep.py").read_text(encoding="utf-8")
        self.assertIn("scripts/archive_intake.py", text)
        self.assertNotIn("intake_page", text)
        self.assertNotIn("K12_FILE_DIR", text)


class ArchivedReadTest(unittest.TestCase):
    def test_archived_photo_and_new_run_are_410_and_review_stays(self) -> None:
        paper = freeze_paper(
            paper_id="paper-r10-http",
            teacher_id=ACTOR_TEACHER_ID,
            student_id=BAIT_STUDENT,
            subject_id="math",
            question_version_id="q-v1",
            answer_version_id="a-v1",
            asset_ids=(),
            layout_template_id="",
            review_version_id="rev-1",
            printed_external_id=BAIT_EXT,
        )
        self.assertNotIsInstance(paper, Err)
        assert not isinstance(paper, Err)
        page = IntakePage(
            intake_id="in-r10-http",
            paper_id=paper.paper_id,
            page_no=1,
            file_id="file-" + "ab" * 8,
            checksum="cd" * 32,
            uploaded_by=ACTOR_TEACHER_ID,
            uploaded_at=OLD,
            located_by="manual",
            archived_at=OLD,
        )

        class _Practice:
            def get_paper(self, paper_id: str) -> object:
                return paper if paper_id == paper.paper_id else None

        class _Intake:
            def get(self, intake_id: str) -> IntakePage | None:
                return page if intake_id == page.intake_id else None

        class _Files:
            def read(self, file_id: str) -> bytes:
                raise AssertionError(file_id)

        class _Stores:
            intake = _Intake()
            practice = _Practice()
            items = None
            files = None

        logger = _Log()
        image = read_intake_image(
            intake_id=page.intake_id,
            actor_id=ACTOR_TEACHER_ID,
            actor_role="teacher",
            practice=_Practice(),
            files=_Files(),
            intake=_Intake(),
            logger=logger,
            request_id="req-r10",
        )
        self.assertIsInstance(image, Err)
        assert isinstance(image, Err)
        self.assertEqual(image.code, "intake_archived")
        started = start_run(
            intake_id=page.intake_id,
            actor_id=ACTOR_TEACHER_ID,
            actor_role="teacher",
            stores=_Stores(),
            runs=MemoryRuns(),
            logger=logger,
            request_id="req-r10-run",
        )
        self.assertIsInstance(started, Err)
        assert isinstance(started, Err)
        self.assertEqual(started.code, "intake_archived")
        self.assertIsNone(load_context(_Stores(), _run_row(page.intake_id)))

    def test_http_returns_410_and_keeps_review_and_accuracy(self) -> None:
        env = {
            "K12_LOG_FILE": "0",
            "K12_PG_DSN": "",
            "K12_ENV": "development",
            "K12_AI_PROVIDER": "mock",
            "K12_AI_MOCK": "ok",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            app = create_app(seed=True)
            with TestClient(app) as client:
                token = _login(client, ACTOR_TEACHER_ID)
                _plant(app)
                paper_id = _issue(client, token)
                app.state.loop.items.set_items(paper_id, (_item(paper_id, 1, BAIT_STEM),))  # type: ignore[attr-defined]
                uploaded = client.put(
                    "/api/practice/papers/" + paper_id + "/pages/1/intake?located_by=manual",
                    content=_jpeg(),
                    headers={"Content-Type": "image/jpeg", "X-K12-CSRF": token},
                )
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                intake_id = str(uploaded.json()["intake_id"])
                app.state.loop.ai_runs.insert(_run_row(intake_id, paper_id))  # type: ignore[attr-defined]
                decided = client.put(
                    "/api/practice/papers/" + paper_id + "/items/1/decision",
                    json={"action": "manual", "verdict": "correct", "comment": BAIT_COMMENT},
                    headers={"X-K12-CSRF": token},
                )
                self.assertEqual(decided.status_code, 200, decided.text)
                _login(client, ACTOR_ADMIN_ID)
                before = client.get("/api/admin/ai/accuracy")
                self.assertEqual(before.status_code, 200, before.text)
                app.state.loop.intake.mark_archived((intake_id,), OLD)  # type: ignore[attr-defined]
                token = _login(client, ACTOR_TEACHER_ID)
                image = client.get("/api/practice/intake/" + intake_id + "/image")
                refused = client.post(
                    "/api/practice/intake/" + intake_id + "/ai-runs",
                    headers={"X-K12-CSRF": token},
                )
                review = client.get("/api/practice/papers/" + paper_id + "/review")
                _login(client, ACTOR_ADMIN_ID)
                after = client.get("/api/admin/ai/accuracy")
        self.assertEqual(image.status_code, 410, image.text)
        self.assertEqual(image.json()["code"], "intake_archived")
        self.assertEqual(refused.status_code, 410, refused.text)
        self.assertEqual(refused.json()["code"], "intake_archived")
        self.assertEqual(review.status_code, 200, review.text)
        body = review.json()
        self.assertEqual(body["confirmed"], 1)
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["decision"]["verdict"], "correct")
        self.assertEqual(body["items"][0]["decision"]["source"], "manual")
        self.assertEqual(body["items"][0]["suggestion"]["transcription"], BAIT_TRANSCRIPT)
        self.assertEqual(after.status_code, 200, after.text)
        self.assertEqual(after.json()["items"], before.json()["items"])
        self.assertGreaterEqual(after.json()["items"]["unlinked_manual"], 1)
        self.assertGreaterEqual(after.json()["items"]["decided_total"], 1)
        self.assertNotIn(PHRASE, review.text)


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _page(
    intake_id: str,
    paper_id: str,
    *,
    superseded: str | None,
    purpose: str = "intake",
    archived: str | None = None,
) -> PageView:
    return PageView(
        intake_id,
        paper_id,
        1,
        "file-" + "ab" * 8,
        "cd" * 32,
        purpose,
        None if superseded is None else _at(superseded),
        None if archived is None else _at(archived),
    )


def _item(paper_id: str, order_no: int, stem: str = "synth-stem") -> PracticeItem:
    return PracticeItem(
        paper_id=paper_id,
        order_no=order_no,
        question_version_id="q-v1",
        answer_version_id="a-v1",
        stem_text=stem,
        answer_text="synth-answer",
        page_no=1,
    )


def _decision(decision_id: str, paper_id: str, decided_at: str, comment: str = "") -> TeacherDecision:
    return TeacherDecision(
        decision_id=decision_id,
        paper_id=paper_id,
        order_no=1,
        verdict="correct",
        source="manual",
        decided_by="teacher-r10",
        decided_at=decided_at,
        comment=comment,
    )


def _place(
    intake: MemoryIntake,
    intake_id: str,
    paper_id: str,
    file_id: str,
    checksum: str,
    *,
    superseded: str | None,
) -> None:
    intake.place(
        IntakePage(
            intake_id=intake_id,
            paper_id=paper_id,
            page_no=1,
            file_id=file_id,
            checksum=checksum,
            uploaded_by="teacher-r10",
            uploaded_at=OLD,
            located_by="manual",
            superseded_at=superseded,
        ),
        replace=False,
    )


def _store(
    intake: MemoryIntake,
    files: MemoryFiles,
    intake_id: str,
    paper_id: str,
    data: bytes,
    *,
    superseded: str | None,
    file_id: str = "",
    purpose_page: bool = False,
) -> str:
    if purpose_page:
        digest = hashlib.sha256(data).hexdigest()
        _place(intake, intake_id, paper_id, file_id, digest, superseded=superseded)
        return file_id
    digest = hashlib.sha256(data).hexdigest()
    chosen = file_id or ("file-" + digest[:16])
    files.store_bytes(chosen, data)
    _place(intake, intake_id, paper_id, chosen, digest, superseded=superseded)
    return chosen


class _World:
    def __init__(self) -> None:
        self.intake = MemoryIntake()
        self.items = MemoryPracticeItems()
        self.decisions = MemoryDecisions()
        self.files = MemoryFiles()
        self.log = _Log()
        self.done = b"synth-photo-r10-done"
        self.old = b"synth-photo-r10-old"
        self.open = b"synth-photo-r10-open"
        self.pdf = b"%PDF-synth-r10"
        self.old_id = _store(self.intake, self.files, "in-old", "paper-done", self.old, superseded=OLD)
        self.done_id = _store(self.intake, self.files, "in-done", "paper-done", self.done, superseded=None)
        self.open_id = _store(self.intake, self.files, "in-open", "paper-open", self.open, superseded=None)
        self.pdf_id, _pdf_sum = self.files.add(self.pdf)
        self.items.set_items("paper-done", (_item("paper-done", 1, BAIT_STEM),))
        self.items.set_items("paper-open", (_item("paper-open", 1), _item("paper-open", 2)))
        self.decisions.replace(_decision("d-done", "paper-done", OLD, comment=BAIT_COMMENT))
        self.out = Path(tempfile.mkdtemp(prefix="k12-r10-out-"))


def _world(test: unittest.TestCase) -> _World:
    world = _World()
    test.addCleanup(lambda: _rm(world.out))
    return world


def _rm(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        else:
            child.rmdir()
    path.rmdir()


def _run(world: _World, *, dry_run: bool, encrypt: bool, real: bool = False) -> ArchiveReport:
    if real:
        from scripts.archive_intake import _open, _seal

        seal = _seal
        opener = _open
    else:
        seal = _marker
        opener = lambda _path, _encrypt: True  # noqa: E731
    return run_archive(
        world.intake,
        world.items,
        world.decisions,
        world.files,
        cutoff=CUTOFF,
        now=NOW,
        retention_days=30,
        out_dir=world.out,
        encrypt=encrypt,
        dry_run=dry_run,
        logger=world.log,
        seal=seal,
        opener=opener,
    )


def _marker(
    items: tuple[ArchiveItem, ...],
    _blobs: dict[str, bytes],
    _now: datetime,
    _cutoff: datetime,
    _days: int,
    out_dir: Path,
    encrypt: bool,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("marker.tar.gz.enc" if encrypt else "marker.tar.gz")
    path.write_bytes(b"synth-marker")
    del items
    return path


def _manifest_text(path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="k12-r10-read-") as raw:
        work = Path(raw)
        tar_path = work / "bundle.tar.gz"
        openssl_convert(path, tar_path, decrypt=True)
        unpacked = work / "out"
        unpacked.mkdir()
        with tarfile.open(tar_path, "r:gz") as packed:
            packed.extractall(unpacked, filter="data")
        return (unpacked / "archive-manifest.json").read_text(encoding="utf-8")


def _run_row(intake_id: str, paper_id: str = "paper-r10-http") -> Run:
    return Run(
        run_id="run-r10-http",
        intake_id=intake_id,
        provider="mock",
        model="mock",
        prompt_version="synth-v1",
        status="succeeded",
        started_at=OLD,
        finished_at=OLD,
        suggestions=(
            Suggestion(
                run_id="run-r10-http",
                paper_id=paper_id,
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


def _jpeg() -> bytes:
    payload = b"IMAGE-BYTES-SYNTH-R10"
    length = len(payload) + 2
    segment = bytes((0xFF, 0xDA, (length >> 8) & 0xFF, length & 0xFF)) + payload
    return b"\xff\xd8" + segment + b"\xff\xd9"


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/login", json={"username": username, "secret": SYNTH_SECRET})
    if response.status_code != 200:
        raise AssertionError(response.text)
    return str(response.json()["csrf_token"])


def _issue(client: TestClient, token: str) -> str:
    published = client.post("/api/catalog/q-v1/publish", headers={"X-K12-CSRF": token})
    if published.status_code != 200:
        raise AssertionError(published.text)
    opened = client.post(
        "/api/practice/papers",
        json={
            "student_id": BAIT_STUDENT,
            "subject_id": "math",
            "question_version_id": "q-v1",
            "review_version_id": "rev-1",
        },
        headers={"X-K12-CSRF": token},
    )
    if opened.status_code != 200:
        raise AssertionError(opened.text)
    return str(opened.json()["paper_id"])


def _plant(app: object) -> None:
    identity = app.state.loop.identity  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    if identity.students.by_id(BAIT_STUDENT) is None:
        identity.students.insert(
            Student(
                student_id=BAIT_STUDENT,
                external_id=BAIT_EXT,
                name="synth-name-r10",
                grade="g7",
                subject_id="math",
                status="active",
                created_by=ACTOR_TEACHER_ID,
                created_at=now,
                updated_at=now,
            )
        )
        identity.grants.insert(
            Grant(
                grant_id=str(uuid.uuid4()),
                teacher_id=ACTOR_TEACHER_ID,
                student_id=BAIT_STUDENT,
                subject_id="math",
                granted_by=ACTOR_TEACHER_ID,
                granted_at=now,
            )
        )


if __name__ == "__main__":
    unittest.main()
