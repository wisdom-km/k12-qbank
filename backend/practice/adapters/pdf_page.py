"""One-page synthetic PDF. Helvetica only, so the product renderer stays unchosen.

The page shows the formula, the answer, the synthetic student number, and a page
number. It does not print a student name.
"""

from __future__ import annotations

from backend.kernel.result import Err
from backend.practice.domain.page_face import PaperPage


class StdPdf:
    """Write one PDF 1.4 page with the built-in Helvetica font. No renderer package."""

    def render(self, page: PaperPage) -> bytes | Err:
        lines = (
            "k12-qbank synthetic paper",
            "question " + page.question_version_id,
            "answer-version " + page.answer_version_id,
            "layout " + page.layout_template_id,
            "assets " + " ".join(page.asset_ids),
            "order " + " ".join(page.item_order),
            "formula " + page.formula,
            "answer " + page.answer_text,
            "student " + page.student_id,
            "name-rule omit",
            "page " + str(page.page_number),
        )
        try:
            encoded = [_pdf_text(line) for line in lines]
        except UnicodeEncodeError:
            return Err("not_rendered", "this synthetic page cannot encode the formula")
        return _pdf(encoded)


def _pdf_text(text: str) -> str:
    raw = text.encode("latin-1").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf"]
    y = 780
    for line in lines:
        commands.append(f"1 0 0 1 48 {y} Tm ({line}) Tj")
        y -= 18
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode("ascii")
    contents = (
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"endstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        contents,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii")
        out += body
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)
