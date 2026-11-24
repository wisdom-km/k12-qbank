"""R4b: full stem, four slots, and an explicit missing-font error."""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from io import StringIO
from unittest import mock

from http_client import signed_client

from backend.bootstrap.run_mode import require_pdf_font
from backend.kernel.log_event import LogEvent
from backend.kernel.result import Err
from backend.practice.adapters.pdf_page import StdPdf
from backend.practice.application.render_paper import page_faces
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.page_layout import (
    item_text_lines,
    line_capacity,
    pack_items,
    slot_answer_box,
)
from backend.practice.domain.paper import freeze_paper


def _item(order_no: int, stem: str, options: str = "") -> PracticeItem:
    return PracticeItem(
        paper_id="paper-slots",
        order_no=order_no,
        question_version_id=f"qv-synth-{order_no}",
        answer_version_id=f"av-synth-{order_no}",
        stem_text=stem,
        answer_text="synth-ans-hidden",
        option_text=options,
    )


def _paper(slots_per_page: int):
    frozen = freeze_paper(
        paper_id="paper-slots",
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
        slots_per_page=slots_per_page,
    )
    assert not isinstance(frozen, Err)
    return frozen


class _Capture:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def log(self, event: LogEvent) -> None:
        self.events.append(event)


class PaperSlotTest(unittest.TestCase):
    def test_layout_model_keeps_the_chinese_stem_and_every_option(self) -> None:
        stem = "下列哪一项等于 2"
        options = ("A. 1", "B. 2", "C. 3", "D. 4")
        item = _item(1, stem, "\n".join(options))
        packed = pack_items((item,), 4)
        faces = page_faces(_paper(4), packed)
        self.assertEqual(len(faces), 1)
        slot = faces[0].slots[0]
        self.assertIn(stem, slot.stem)
        for option in options:
            self.assertIn(option, slot.options)
        drawn = StdPdf().render(faces[0])
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        for option in options:
            self.assertIn(option.encode("ascii"), drawn)
        self.assertIn(b"<4E0B>", drawn)
        self.assertIn(b"synth-0001", drawn)
        self.assertIn(b"page 1", drawn)
        self.assertIn(b"pages 1", drawn)
        self.assertNotIn(b"student-synth", drawn)
        self.assertNotIn(b"name-rule", drawn)
        self.assertNotIn(b"synth-ans-hidden", drawn)
        self.assertNotIn("班级", slot.stem)
        self.assertNotIn(b"<73ED>", drawn)
        self.assertNotIn(b"<7EA7>", drawn)

    def test_nine_short_items_fill_three_pages(self) -> None:
        items = tuple(_item(number, f"计算：{number}+1") for number in range(1, 10))
        packed = pack_items(items, 4)
        counts: dict[int, int] = {}
        for item in packed:
            counts[item.page_no] = counts.get(item.page_no, 0) + 1
        self.assertEqual([counts[1], counts[2], counts[3]], [4, 4, 1])
        faces = page_faces(_paper(4), packed)
        self.assertEqual(len(faces), 3)
        self.assertEqual([len(face.slots) for face in faces], [4, 4, 1])

    def test_a_long_stem_uses_more_than_one_slot(self) -> None:
        stem = "超" * 250
        item = _item(1, stem)
        packed = pack_items((item,), 4)
        span = packed[0].slot_span
        lines = item_text_lines(1, stem, ())
        self.assertGreater(span, 1)
        self.assertLessEqual(span, 4)
        self.assertGreater(len(lines), line_capacity(span - 1))
        self.assertLessEqual(len(lines), line_capacity(span))
        self.assertEqual(packed[0].slot_no, 1)
        self.assertEqual(packed[0].page_no, 1)

    def test_the_same_slot_number_always_returns_the_same_box(self) -> None:
        first = slot_answer_box(4, 2, 1)
        second = slot_answer_box(4, 2, 1)
        self.assertEqual(first, second)
        self.assertNotEqual(first, slot_answer_box(4, 3, 1))
        self.assertEqual(slot_answer_box(1, 1, 1), (72, 220, 451, 220))
        self.assertEqual(slot_answer_box(1, 1, 1), slot_answer_box(1, 2, 3))

    def test_old_rows_stay_one_item_per_page(self) -> None:
        items = (
            replace(_item(1, "计算：1+1"), page_no=1, slot_no=1, slot_span=1),
            replace(_item(2, "计算：2+2"), page_no=1, slot_no=1, slot_span=1),
        )
        faces = page_faces(_paper(1), items)
        self.assertEqual(len(faces), 2)
        self.assertEqual(faces[0].slots, ())
        self.assertEqual(faces[1].page_number, 2)
        drawn = StdPdf().render_document(faces)
        self.assertIsInstance(drawn, bytes)
        assert isinstance(drawn, bytes)
        self.assertIn(b"/Count 2", drawn)
        self.assertIn(b"72 220 451 220 re S", drawn)
        self.assertIn(b"formula ", drawn)
        self.assertIn(b"page 1", drawn)
        self.assertIn(b"pages 2", drawn)
        self.assertIn(b"page 2", drawn)

    def test_development_issue_returns_pdf_font_missing(self) -> None:
        empty = tempfile.mkdtemp()
        env = {"WINDIR": empty, "K12_PDF_FONT_PATH": ""}
        with mock.patch("backend.practice.adapters.pdf_font._LINUX", ()):
            with mock.patch.dict(os.environ, env):
                with signed_client() as client:
                    published = client.post("/api/catalog/q-v1/publish")
                    self.assertEqual(published.status_code, 200, published.text)
                    opened = client.post(
                        "/api/practice/papers",
                        json={
                            "teacher_id": "teacher-synth",
                            "student_id": "student-synth",
                            "subject_id": "math",
                            "question_version_id": "q-v1",
                            "review_version_id": "rev-1",
                        },
                    )
                    self.assertEqual(opened.status_code, 200, opened.text)
                    body = opened.json()
                    self.assertEqual(body["status"], "待渲染")
                    self.assertEqual(body["render_code"], "pdf_font_missing")
                    self.assertIn("fonts-noto-cjk", body["render_message"])
                    self.assertIn("K12_PDF_FONT_PATH", body["render_message"])

    def test_production_without_a_font_exits(self) -> None:
        logger = _Capture()
        empty = tempfile.mkdtemp()
        env = {"WINDIR": empty, "K12_PDF_FONT_PATH": ""}
        buffer = StringIO()
        with mock.patch("backend.practice.adapters.pdf_font._LINUX", ()):
            with mock.patch.dict(os.environ, env):
                require_pdf_font("development", logger)
                self.assertEqual(logger.events, [])
                with redirect_stderr(buffer):
                    with self.assertRaises(SystemExit) as caught:
                        require_pdf_font("production", logger)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(logger.events[0].outcome, "pdf_font_missing")
        text = buffer.getvalue()
        self.assertIn("fonts-noto-cjk", text)
        self.assertIn("K12_PDF_FONT_PATH", text)
        self.assertIn("msyh.ttc", text)
