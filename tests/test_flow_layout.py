"""Flow layout stores answer boxes. Old slot papers stay on the slot path."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest import mock

from http_client import signed_client

from backend.bootstrap.http_app import _default_app
from backend.bootstrap.run_mode import require_paper_layout
from backend.catalog.api import resolved_space
from backend.kernel.log_event import LogEvent
from backend.practice.adapters.memory import MemoryPractice
from backend.practice.adapters.memory_items import MemoryComposedWriter, MemoryPracticeItems
from backend.practice.adapters.pdf_page import StdPdf, _num
from backend.practice.application.render_paper import page_faces
from backend.practice.domain.flow_layout import (
    FlowQuestion,
    ItemTooLong,
    blank_count,
    dump_layout,
    flow_place,
    header_text,
)
from backend.practice.domain.item import ItemBox, PracticeItem
from backend.practice.domain.layout_params import LayoutError, bundled_layout_path, load_layout
from backend.practice.domain.paper import freeze_paper

ISSUE = {
    "teacher_id": "teacher-synth",
    "student_id": "student-synth",
    "subject_id": "math",
    "question_version_id": "q-v1",
    "review_version_id": "rev-1",
}


def _params():
    loaded = load_layout()
    if isinstance(loaded, LayoutError):
        raise AssertionError(loaded.message)
    return loaded


def _choice(order_no: int, stem: str, options: tuple[str, ...] = ("A. 2",)) -> FlowQuestion:
    return FlowQuestion(order_no, f"qv-synth-{order_no}", stem, options, "letter", 1)


class _Capture:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class FlowLayoutTest(unittest.TestCase):
    def test_eight_choices_share_one_page_with_one_letter_box_each(self) -> None:
        params = _params()
        long_option = "A. " + ("synth-option-" * 12)
        questions = tuple(_choice(number, f"synth-choice-{number}") for number in range(1, 8))
        questions += (_choice(8, "synth-choice-8", (long_option, "B. 3")),)
        placed = flow_place(questions, params)
        self.assertNotIsInstance(placed, ItemTooLong)
        assert not isinstance(placed, ItemTooLong)
        self.assertEqual([item.page_no for item in placed], [1, 1, 1, 1, 1, 1, 1, 1])
        self.assertEqual([len(item.boxes) for item in placed], [1] * 8)
        right = params.page_width - params.margin_right - params.letter_width
        for item in placed:
            box = item.boxes[0]
            self.assertEqual(box.kind, "letter")
            self.assertEqual((box.w, box.h), (params.letter_width, params.letter_height))
            self.assertEqual(box.x, right)
        again = flow_place(questions, params)
        self.assertEqual(again, placed)

    def test_two_underscore_blanks_make_two_boxes(self) -> None:
        stem = "3 + ____ = ____"
        self.assertEqual(blank_count(stem), 2)
        self.assertEqual(blank_count("（ ）"), 1)
        question = FlowQuestion(1, "qv-synth-blank", stem, (), "blanks", blank_count(stem))
        placed = flow_place((question,), _params())
        self.assertNotIsInstance(placed, ItemTooLong)
        assert not isinstance(placed, ItemTooLong)
        self.assertEqual(len(placed[0].boxes), 2)
        self.assertEqual([box.kind for box in placed[0].boxes], ["blanks", "blanks"])
        self.assertEqual([box.w for box in placed[0].boxes], [36.0, 36.0])
        self.assertEqual([box.h for box in placed[0].boxes], [20.0, 20.0])
        joined = "".join(line.text for line in placed[0].lines)
        self.assertIn(stem, joined)

    def test_solution_defaults_to_large_and_full_fills_the_rest(self) -> None:
        self.assertEqual(resolved_space(None, "solution"), ("large", True))
        self.assertEqual(resolved_space(None, "single_choice"), ("letter", True))
        self.assertEqual(resolved_space(None, "fill_blank"), ("blanks", True))
        self.assertEqual(resolved_space(None, "unresolved"), ("medium", True))
        self.assertEqual(resolved_space("full", "solution"), ("full", False))
        params = _params()
        placed = flow_place(
            (
                FlowQuestion(1, "qv-synth-large", "synth-worked", (), "large", 1),
                FlowQuestion(2, "qv-synth-full", "synth-full", (), "full", 1),
            ),
            params,
        )
        self.assertNotIsInstance(placed, ItemTooLong)
        assert not isinstance(placed, ItemTooLong)
        self.assertEqual(placed[0].boxes[0].kind, "large")
        self.assertEqual(placed[0].boxes[0].h, params.large_height)
        full = placed[1].boxes[0]
        self.assertEqual(full.kind, "full")
        self.assertEqual(full.y, params.margin_bottom)
        self.assertGreater(full.h, params.large_height)
        self.assertEqual(full.w, params.page_width - params.margin_left - params.margin_right)

    def test_a_stem_that_fits_keeps_every_character_and_a_longer_one_is_refused(self) -> None:
        params = _params()
        short = "甲" * 200
        fitting = flow_place((FlowQuestion(1, "qv-synth-fit", short, (), "large", 1),), params)
        self.assertNotIsInstance(fitting, ItemTooLong)
        assert not isinstance(fitting, ItemTooLong)
        self.assertIn(short, "".join(line.text for line in fitting[0].lines))
        long = "甲" * 8000
        refused = flow_place((FlowQuestion(1, "qv-synth-long", long, (), "large", 1),), params)
        self.assertIsInstance(refused, ItemTooLong)
        assert isinstance(refused, ItemTooLong)
        self.assertEqual(refused.order_no, 1)
        self.assertEqual(refused.question_version_id, "qv-synth-long")
        self.assertNotIsInstance(refused, tuple)

    def test_header_prints_the_external_id_and_the_page_label(self) -> None:
        text = header_text("synth-0001", 2, 3)
        self.assertEqual(text, "synth-0001  第 2 页 / 共 3 页")
        self.assertNotIn("student-", text)
        self.assertNotIn("姓名", text)
        self.assertNotIn("班级", text)

    def test_each_floor_names_its_field(self) -> None:
        floors = {
            "qr_module": 1.6,
            "qr_quiet_modules": 3,
            "mark_size": 11,
            "header_font_size": 8,
            "letter_width": 27,
            "letter_height": 19,
        }
        raw = json.loads(bundled_layout_path().read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            for field, value in floors.items():
                broken = dict(raw)
                broken[field] = value
                path = Path(folder) / (field + ".json")
                path.write_text(json.dumps(broken), encoding="utf-8")
                loaded = load_layout(path)
                self.assertIsInstance(loaded, LayoutError)
                assert isinstance(loaded, LayoutError)
                self.assertEqual(loaded.field, field)
                self.assertIn(field, loaded.message)
                self.assertIn("小于下限", loaded.message)

    def test_production_refuses_a_bad_layout_and_development_does_not(self) -> None:
        raw = json.loads(bundled_layout_path().read_text(encoding="utf-8"))
        raw["qr_module"] = 1.0
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "layout.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            env = {
                "K12_ENV": "production",
                "K12_PG_DSN": "postgresql://k12:changeme@127.0.0.1:1/unused",
                "K12_FILE_DIR": folder,
                "K12_PAPER_LAYOUT_PATH": str(path),
                "K12_CORS_ORIGINS": "http://127.0.0.1:5173",
            }
            stdout = StringIO()
            stderr = StringIO()
            with mock.patch("backend.bootstrap.run_mode.load_system_face", return_value=object()):
                with mock.patch.dict(os.environ, env):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as caught:
                            _default_app()
            self.assertEqual(caught.exception.code, 1)
            logged = json.loads(stdout.getvalue().strip().splitlines()[-1])
            self.assertEqual(logged["event"], "startup_refused")
            self.assertEqual(logged["outcome"], "layout_invalid:qr_module")
            self.assertIn("qr_module", stderr.getvalue())
            self.assertNotIn("postgresql://", stdout.getvalue())
            self.assertNotIn("changeme", stdout.getvalue())
            development = dict(env, K12_ENV="development", K12_PG_DSN="")
            with mock.patch.dict(os.environ, development):
                require_paper_layout("development", _Capture())
                app = _default_app()
            self.assertIsNotNone(app)


class FlowIssueTest(unittest.TestCase):
    def test_catalog_returns_the_type_default(self) -> None:
        with signed_client() as client:
            listed = client.get("/api/catalog")
            self.assertEqual(listed.status_code, 200, listed.text)
            row = listed.json()["items"][0]
            self.assertEqual(row["answer_space"], "medium")
            self.assertTrue(row["answer_space_is_default"])
            self.assertEqual(row["formula_note"], "公式未结构化")
            one = client.get("/api/catalog/q-v1")
            self.assertEqual(one.json()["answer_space"], "medium")
            self.assertTrue(one.json()["answer_space_is_default"])
            self.assertEqual(one.json()["formula_note"], "公式未结构化")

    def test_issue_stores_the_boxes_and_a_later_file_does_not_move_them(self) -> None:
        raw = json.loads(bundled_layout_path().read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "layout.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            env = {"K12_PAPER_LAYOUT_PATH": str(path), "K12_PAPER_QR": "on"}
            with mock.patch.dict(os.environ, env):
                with signed_client() as client:
                    self._publish(client)
                    opened = client.post("/api/practice/papers", json=ISSUE)
                    self.assertEqual(opened.status_code, 200, opened.text)
                    body = opened.json()
                    paper_id = body["paper_id"]
                    stored = client.app.state.loop.practice.get_paper(paper_id)
                    items = client.app.state.loop.items.items_of(paper_id)
                    first_box = items[0].boxes[0]
                    first_chrome = stored.layout_params
                    pdf = client.get("/api/practice/files/" + body["file_id"]).content
                    token = f"{_num(first_box.x)} {_num(first_box.y)} {_num(first_box.w)} {_num(first_box.h)} re S"
                    self.assertIn(token.encode("ascii"), pdf)
                    self.assertIn(b"1.8 1.8 re f", pdf)
                    face = page_faces(stored, tuple(items))[0]
                    self.assertEqual(face.flow_lines[0][0], "synth-0001  第 1 页 / 共 1 页")
                    self.assertIsNotNone(face.flow_qr)
                    assert face.flow_qr is not None
                    self.assertEqual(face.flow_qr[2], 1.8)
                    raw["qr_module"] = 2.0
                    raw["medium_height"] = 200
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    again = page_faces(client.app.state.loop.practice.get_paper(paper_id), tuple(items))
                    self.assertEqual(again[0].flow_boxes[0][3], first_box.h)
                    self.assertEqual(client.app.state.loop.practice.get_paper(paper_id).layout_params, first_chrome)
                    second = client.post("/api/practice/papers", json=dict(ISSUE, student_id="student-synth-2"))
                    self.assertEqual(second.status_code, 200, second.text)
                    moved = client.app.state.loop.items.items_of(second.json()["paper_id"])
                    self.assertEqual(moved[0].boxes[0].h, 200)
                    kept = client.app.state.loop.items.items_of(paper_id)
                    self.assertEqual(kept[0].boxes[0].h, first_box.h)
                    self.assertEqual(kept[0].boxes[0].y, first_box.y)

    def test_qr_off_prints_no_module(self) -> None:
        with mock.patch.dict(os.environ, {"K12_PAPER_QR": "off"}):
            with signed_client() as client:
                self._publish(client)
                opened = client.post("/api/practice/papers", json=ISSUE)
                self.assertEqual(opened.status_code, 200, opened.text)
                self.assertFalse(opened.json()["qr_printed"])
                pdf = client.get("/api/practice/files/" + opened.json()["file_id"]).content
                self.assertNotIn(b"1.8 1.8 re f", pdf)
                self.assertIn(b"synth-0001", pdf)
                self.assertNotIn(b"student-synth", pdf)
                self.assertNotIn(b"name-rule omit", pdf)

    def test_item_too_long_refuses_the_issue_and_names_the_question(self) -> None:
        with signed_client() as client:
            self._publish(client)
            live = client.app.state.loop.approvals.read_snapshot("q-v1")
            assert live is not None
            client.app.state.loop.approvals.put(replace(live, stem="甲" * 8000))
            opened = client.post("/api/practice/papers", json=ISSUE)
            self.assertEqual(opened.status_code, 409, opened.text)
            body = opened.json()
            self.assertEqual(body["code"], "item_too_long")
            self.assertIn("第 1 题", body["message"])
            self.assertIn("q-v1", body["message"])
            self.assertNotIn("甲甲", body["message"])
            self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)

    def test_development_issue_returns_layout_invalid(self) -> None:
        raw = json.loads(bundled_layout_path().read_text(encoding="utf-8"))
        raw["letter_height"] = 10
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "layout.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with mock.patch.dict(os.environ, {"K12_PAPER_LAYOUT_PATH": str(path)}):
                with signed_client() as client:
                    self._publish(client)
                    opened = client.post("/api/practice/papers", json=ISSUE)
                    self.assertEqual(opened.status_code, 409, opened.text)
                    body = opened.json()
                    self.assertEqual(body["code"], "layout_invalid")
                    self.assertIn("letter_height", body["message"])
                    self.assertEqual(client.get("/api/practice/papers").json()["count"], 0)

    def _publish(self, client: object) -> None:
        response = client.post("/api/catalog/q-v1/publish")  # type: ignore[attr-defined]
        self.assertEqual(response.status_code, 200, response.text)


class FlowBoxStoreTest(unittest.TestCase):
    def test_memory_round_trip_keeps_the_placed_box(self) -> None:
        store = MemoryPractice()
        items = MemoryPracticeItems()
        paper, item = _issued_item()
        MemoryComposedWriter(store, items).place_composed(paper, (item,))
        loaded = items.items_of(paper.paper_id)
        self.assertEqual(loaded[0].boxes, item.boxes)
        self.assertEqual(loaded[0].placed_lines, item.placed_lines)
        face = page_faces(paper, loaded)[0]
        box = loaded[0].boxes[0]
        self.assertEqual(face.flow_boxes[0], (box.x, box.y, box.w, box.h))
        drawn = StdPdf().render(face)
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        token = f"{_num(box.x)} {_num(box.y)} {_num(box.w)} {_num(box.h)} re S".encode("ascii")
        self.assertIn(token, drawn)

    @unittest.skipUnless(os.environ.get("K12_PG_DSN", "").strip(), "K12_PG_DSN is not set")
    def test_pg_round_trip_keeps_the_placed_box(self) -> None:
        from psycopg_pool import ConnectionPool

        from backend.bootstrap.compose import repo_root
        from backend.bootstrap.migrate import migrate
        from backend.practice.adapters.pg_items import PgPracticeItems

        dsn = os.environ["K12_PG_DSN"]
        migrate(dsn, repo_root(), "up")
        pool = ConnectionPool(dsn, min_size=1, max_size=1, open=True)
        try:
            port = PgPracticeItems(pool)
            paper, item = _issued_item()
            port.place_composed(paper, (item,))
            loaded = port.items_of(paper.paper_id)
            self.assertEqual(loaded[0].boxes, item.boxes)
            self.assertEqual(loaded[0].placed_lines, item.placed_lines)
            _delete_paper(pool, paper.paper_id)
            self.assertEqual(port.items_of(paper.paper_id), ())
        finally:
            pool.close()


def _issued_item() -> tuple[object, PracticeItem]:
    from backend.kernel.result import Err

    params = _params()
    placed = flow_place((_choice(1, "synth-choice"),), params)
    assert not isinstance(placed, ItemTooLong)
    drawn = placed[0]
    frozen = freeze_paper(
        paper_id="paper-r4d-box",
        teacher_id="teacher-synth",
        student_id="student-synth",
        subject_id="math",
        question_version_id="qv-synth-1",
        answer_version_id="av-synth-1",
        asset_ids=(),
        layout_template_id="",
        review_version_id="rev-synth",
        item_order=("sq-1",),
        printed_external_id="synth-0001",
        slots_per_page=1,
        layout_kind="flow",
        layout_params=dump_layout(params),
    )
    assert not isinstance(frozen, Err)
    item = PracticeItem(
        paper_id=frozen.paper_id,
        order_no=1,
        question_version_id="qv-synth-1",
        answer_version_id="av-synth-1",
        stem_text="synth-choice",
        answer_text="synth-hidden",
        page_no=drawn.page_no,
        placed_lines=tuple((line.text, line.x, line.y) for line in drawn.lines),
        boxes=tuple(
            ItemBox(box.box_no, box.page_no, box.x, box.y, box.w, box.h, box.kind) for box in drawn.boxes
        ),
    )
    return frozen, item


def _delete_paper(pool: object, paper_id: str) -> None:
    statements = (
        "DELETE FROM practice_item_box WHERE paper_id = %s",
        "DELETE FROM practice_item WHERE paper_id = %s",
        "DELETE FROM paper_pages WHERE paper_id = %s",
        "DELETE FROM papers WHERE paper_id = %s",
    )
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            for statement in statements:
                conn.execute(statement, (paper_id,))
