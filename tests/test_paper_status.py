"""Paper status rules without a PDF renderer."""

from __future__ import annotations

import unittest

from backend.kernel.result import Err
from backend.practice.domain.paper import Paper, freeze_paper, mark_issued, mark_printable, recall_file


def sample() -> Paper:
    frozen = freeze_paper(
        paper_id="paper-1",
        teacher_id="teacher-synth",
        student_id="student-synth",
        subject_id="math",
        question_version_id="q-v1",
        answer_version_id="a-v1",
        asset_ids=("page-synth",),
        layout_template_id="layout-1",
        review_version_id="rev-1",
        item_order=("sq-1",),
    )
    if isinstance(frozen, Err):
        raise AssertionError(frozen.code)
    return frozen


class PaperStatusTest(unittest.TestCase):
    def test_issue_stays_waiting_for_render(self) -> None:
        paper = sample()
        self.assertEqual(paper.status, "待渲染")
        self.assertIsNone(paper.file_id)
        self.assertIsNone(paper.file_checksum)
        self.assertEqual(paper.item_order, ("sq-1",))

    def test_printable_needs_a_file_and_checksum(self) -> None:
        paper = sample()
        missing = mark_printable(paper, file_id="", checksum="abc")
        self.assertIsInstance(missing, Err)
        ready = mark_printable(paper, file_id="file-1", checksum="sum-1")
        self.assertIsInstance(ready, Paper)
        assert isinstance(ready, Paper)
        self.assertEqual(ready.status, "可打印")
        self.assertEqual(paper.status, "待渲染")
        self.assertEqual(paper.file_id, None)

    def test_hand_out_stops_when_the_publication_is_retired(self) -> None:
        paper = sample()
        ready = mark_printable(paper, file_id="file-1", checksum="sum-1")
        assert isinstance(ready, Paper)
        refused = mark_issued(ready, publication_retired=True)
        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertEqual(refused.code, "retired")
        self.assertEqual(ready.status, "可打印")
        issued = mark_issued(ready, publication_retired=False)
        assert isinstance(issued, Paper)
        self.assertEqual(issued.status, "已发放")
        self.assertEqual(issued.file_id, "file-1")

    def test_changed_checksum_keeps_the_old_file_id(self) -> None:
        paper = sample()
        ready = mark_printable(paper, file_id="file-1", checksum="sum-1")
        assert isinstance(ready, Paper)
        changed = recall_file(ready, file_id="file-1", checksum="sum-2")
        self.assertIsInstance(changed, Err)
        assert isinstance(changed, Err)
        self.assertEqual(changed.code, "file_changed")
        self.assertEqual(ready.file_id, "file-1")
        self.assertEqual(ready.file_checksum, "sum-1")
        self.assertIsNone(recall_file(ready, file_id="file-1", checksum="sum-1"))


if __name__ == "__main__":
    unittest.main()
