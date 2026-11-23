"""Synthetic PDF. Latin text stays on the built-in Helvetica face.

The page shows the printed student number, the page numbers, the formula,
corner marks, a fixed answer box, and an optional QR code.
It does not print a name, a class, or the internal student id. The Chinese
label in front of the formula stays off the page (ADR 0024). The question
and the answer stay on the practice item. The QR code is
drawn as rectangles. Its payload is not a literal string in the file.
Latin text uses WinAnsiEncoding. Chinese uses the installed KaiTi, Microsoft
YaHei, or SimHei face and embeds only this document's glyphs.
A character neither face can take is a stable render error.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.kernel.result import Err
from backend.practice.adapters.pdf_font import PageFont, load_system_face, subset_page_font
from backend.practice.domain.page_face import PaperPage
from backend.practice.domain.page_layout import alignment_marks, answer_box, qr_origin
from backend.practice.domain.qr_code import encode_qr, qr_payload


class StdPdf:
    """Write a PDF 1.4 document. Latin uses Helvetica. Chinese uses the system face."""

    def render(self, page: PaperPage) -> bytes | Err:
        return self.render_document((page,))

    def render_document(self, pages: Sequence[PaperPage]) -> bytes | Err:
        prepared: list[tuple[tuple[str, ...], list[str]]] = []
        for page in pages:
            try:
                prepared.append((_lines(page), _graphics(page)))
            except (ValueError, RuntimeError):
                return Err("not_rendered", "this synthetic page cannot encode the formula")
        try:
            if any(_has_cjk(line) for lines, _ in prepared for line in lines):
                return _pdf_cjk(prepared)
            encoded = [tuple(_pdf_text(line) for line in lines) for lines, _ in prepared]
            marks = [graphics for _, graphics in prepared]
            return _pdf(encoded, marks)
        except UnicodeEncodeError:
            return Err("not_rendered", "this synthetic page cannot encode the formula")


def _lines(page: PaperPage) -> tuple[str, ...]:
    lines: list[str] = []
    if page.printed_external_id:
        lines.append(page.printed_external_id)
    lines.append("page " + str(page.page_number))
    lines.append("pages " + str(page.page_count))
    if page.formula:
        lines.append("formula " + page.formula)
    return tuple(lines)


def _graphics(page: PaperPage) -> list[str]:
    commands = ["0 0 0 rg", "0 0 0 RG", "1.5 w"]
    for left, bottom, width, height in alignment_marks():
        commands.append(f"{left} {bottom} {width} {height} re f")
    left, bottom, width, height = answer_box(max(page.page_number, 1))
    commands.append(f"{left} {bottom} {width} {height} re S")
    if not page.qr_printed:
        return commands
    matrix = encode_qr(qr_payload(page.paper_id, page.page_number))
    origin_x, origin_y, module = qr_origin()
    size = len(matrix)
    for row, cells in enumerate(matrix):
        for col, dark in enumerate(cells):
            if not dark:
                continue
            x = origin_x + col * module
            y = origin_y + (size - 1 - row) * module
            commands.append(f"{x} {y} {module} {module} re f")
    return commands


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


def _pdf(pages: list[tuple[str, ...]], graphics: list[list[str]]) -> bytes:
    contents = [_latin_stream(lines, marks) for lines, marks in zip(pages, graphics)]
    font_at = 3 + 2 * len(contents)
    resources = f"<< /Font << /F1 {font_at} 0 R >> >>".encode("ascii")
    trailing = [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    return _assemble(contents, resources, trailing)


def _latin_stream(lines: tuple[str, ...], graphics: list[str]) -> bytes:
    commands = list(graphics)
    commands.extend(["BT", "/F1 12 Tf"])
    y = 780
    for line in lines:
        commands.append(f"1 0 0 1 48 {y} Tm ({line}) Tj")
        y -= 18
    commands.append("ET")
    return ("\n".join(commands) + "\n").encode("latin-1")


def _pdf_cjk(prepared: list[tuple[tuple[str, ...], list[str]]]) -> bytes:
    codes: set[int] = set()
    for lines, _ in prepared:
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
    contents = [_cjk_stream(lines, marks, font) for lines, marks in prepared]
    font_at = 3 + 2 * len(contents)
    resources = f"<< /Font << /F1 {font_at} 0 R /F2 {font_at + 1} 0 R >> >>".encode("ascii")
    return _assemble(contents, resources, _cjk_fonts(font, codes, font_at))


def _cjk_stream(lines: tuple[str, ...], graphics: list[str], font: PageFont) -> bytes:
    commands = list(graphics)
    commands.append("BT")
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
    return ("\n".join(commands) + "\n").encode("latin-1")


def _cjk_fonts(font: PageFont, codes: set[int], font_at: int) -> list[bytes]:
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
    return [
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        (
            f"<< /Type /Font /Subtype /Type0 /BaseFont /K12QBK+{font.name} "
            f"/Encoding /Identity-H /DescendantFonts [{font_at + 2} 0 R] /ToUnicode {font_at + 5} 0 R >>"
        ).encode("ascii"),
        (
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /K12QBK+{font.name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {font_at + 3} 0 R /CIDToGIDMap /Identity /W [{widths}] >>"
        ).encode("ascii"),
        (
            f"<< /Type /FontDescriptor /FontName /K12QBK+{font.name} /Flags 4 "
            f"/FontBBox [{x0} {y0} {x1} {y1}] /ItalicAngle 0 "
            f"/Ascent {font.ascent} /Descent {font.descent} /CapHeight {font.ascent} "
            f"/StemV 80 /FontFile2 {font_at + 4} 0 R >>"
        ).encode("ascii"),
        _stream(font.ttf, length1=True),
        _stream(unicode_map),
    ]


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


def _assemble(contents: list[bytes], resources: bytes, trailing: list[bytes]) -> bytes:
    count = len(contents)
    kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode("ascii"),
    ]
    for index, stream in enumerate(contents):
        content_id = 4 + 2 * index
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Contents {content_id} 0 R /Resources {resources.decode('ascii')} >>"
            ).encode("ascii")
        )
        objects.append(_stream(stream))
    objects.extend(trailing)
    return _finish(objects)


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
