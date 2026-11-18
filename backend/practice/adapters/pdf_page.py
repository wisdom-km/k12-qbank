"""One-page synthetic PDF. Latin text stays on the built-in Helvetica face.

The page shows the frozen formula, the synthetic student number, the paper
instance, and the page numbers. It does not print a name, an answer, or an
explanation. Latin text uses WinAnsiEncoding. Without that encoding, Helvetica
uses StandardEncoding, byte D7 has no glyph, and a formula such as 2×3 is
drawn as 23. Chinese uses the installed KaiTi, Microsoft YaHei, or SimHei
face and embeds only this page's glyphs. The font file is not stored here.
A character neither face can take is a stable render error.
"""

from __future__ import annotations

from backend.kernel.result import Err
from backend.practice.adapters.pdf_font import PageFont, load_system_face, subset_page_font
from backend.practice.domain.page_face import PaperPage


class StdPdf:
    """Write one PDF 1.4 page. Latin uses Helvetica. Chinese uses the system face."""

    def render(self, page: PaperPage) -> bytes | Err:
        lines = (
            "k12-qbank synthetic paper",
            "question " + page.question_version_id,
            "answer-version " + page.answer_version_id,
            "layout " + page.layout_template_id,
            "assets " + " ".join(page.asset_ids),
            "order " + " ".join(page.item_order),
            "formula " + page.formula,
            "student " + page.student_id,
            "name-rule omit",
            "paper " + page.paper_id,
            "page " + str(page.page_number),
            "pages " + str(page.page_count),
        )
        try:
            if any(_has_cjk(line) for line in lines):
                return _pdf_cjk(lines)
            encoded = [_pdf_text(line) for line in lines]
            return _pdf(encoded)
        except UnicodeEncodeError:
            return Err("not_rendered", "this synthetic page cannot encode the formula")


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0x3000 <= code <= 0x303F
        or 0xFF00 <= code <= 0xFFEF
    )


def _has_cjk(text: str) -> bool:
    return any(_is_cjk(char) for char in text)


def _pdf_text(text: str) -> str:
    for index, char in enumerate(text):
        if ord(char) < 32 or ord(char) == 127:
            raise UnicodeEncodeError("cp1252", text, index, index + 1, "control")
    raw = text.encode("cp1252").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf"]
    y = 780
    for line in lines:
        commands.append(f"1 0 0 1 48 {y} Tm ({line}) Tj")
        y -= 18
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode("latin-1")
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
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
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


def _pdf_cjk(lines: list[str]) -> bytes:
    codes: set[int] = set()
    for line in lines:
        for char in line:
            if _is_cjk(char):
                codes.add(ord(char))
            else:
                _pdf_text(char)
    face = load_system_face()
    if face is None:
        raise UnicodeEncodeError("cp1252", "cjk", 0, 1, "no system face")
    font = subset_page_font(face, codes)
    if font is None:
        raise UnicodeEncodeError("cp1252", "cjk", 0, 1, "glyph missing")
    commands = ["BT"]
    y = 780
    for line in lines:
        commands.append(f"1 0 0 1 48 {y} Tm")
        for kind, run in _runs(line):
            if kind == "cjk":
                glyphs = "".join(f"{font.glyph_id[ord(char)]:04X}" for char in run)
                commands.append(f"/F2 12 Tf <{glyphs}> Tj")
            else:
                commands.append(f"/F1 12 Tf ({_pdf_text(run)}) Tj")
        y -= 18
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode("latin-1")
    x0, y0, x1, y1 = font.bbox
    widths = " ".join(f"{font.glyph_id[code]} [{font.width[code]}]" for code in sorted(codes))
    unicode_map = (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\n"
        "begincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n"
        "/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        + _bfchars(font, codes)
        + "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")
    contents = _stream(stream)
    to_unicode = _stream(unicode_map)
    font_file = _stream(font.ttf, length1=True)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        contents,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        (
            f"<< /Type /Font /Subtype /Type0 /BaseFont /K12QBK+{font.name} "
            f"/Encoding /Identity-H /DescendantFonts [7 0 R] /ToUnicode 10 0 R >>"
        ).encode("ascii"),
        (
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /K12QBK+{font.name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor 8 0 R /CIDToGIDMap /Identity /W [{widths}] >>"
        ).encode("ascii"),
        (
            f"<< /Type /FontDescriptor /FontName /K12QBK+{font.name} /Flags 4 "
            f"/FontBBox [{x0} {y0} {x1} {y1}] /ItalicAngle 0 "
            f"/Ascent {font.ascent} /Descent {font.descent} /CapHeight {font.ascent} "
            f"/StemV 80 /FontFile2 9 0 R >>"
        ).encode("ascii"),
        font_file,
        to_unicode,
    ]
    return _finish(objects)


def _bfchars(font: PageFont, codes: set[int]) -> str:
    ordered = sorted(codes)
    blocks: list[str] = []
    for start in range(0, len(ordered), 100):
        chunk = ordered[start : start + 100]
        lines = "\n".join(f"<{font.glyph_id[code]:04X}> <{code:04X}>" for code in chunk)
        blocks.append(f"{len(chunk)} beginbfchar\n{lines}\nendbfchar\n")
    return "".join(blocks)


def _runs(line: str) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    kind = ""
    buf: list[str] = []
    for char in line:
        this = "cjk" if _is_cjk(char) else "latin"
        if kind and this != kind:
            runs.append((kind, "".join(buf)))
            buf = []
        kind = this
        buf.append(char)
    if buf:
        runs.append((kind, "".join(buf)))
    return runs


def _stream(payload: bytes, *, length1: bool = False) -> bytes:
    extra = f" /Length1 {len(payload)}" if length1 else ""
    return (
        f"<< /Length {len(payload)}{extra} >>\nstream\n".encode("ascii")
        + payload
        + b"\nendstream"
    )


def _finish(objects: list[bytes]) -> bytes:
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
