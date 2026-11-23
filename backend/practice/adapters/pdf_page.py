"""Synthetic PDF. Latin text stays on the built-in Helvetica face.

A page with slots prints the question number, the full stem, and the options.
A page without slots keeps the older formula line. Both print the student
number, the page numbers, corner marks, answer boxes, and an optional QR code.
Neither prints a name, a class, or the internal student id. The QR code is
drawn as rectangles. Its payload is not a literal string in the file.
Latin text uses WinAnsiEncoding. Chinese uses the face from pdf_font and
embeds only this document's glyphs, as a TrueType subset or a CFF subset.
A missing face is pdf_font_missing.
A character the loaded face cannot draw is not_rendered.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.kernel.result import Err
from backend.practice.adapters.pdf_font import MISSING_FONT, PageFont, load_system_face, subset_page_font
from backend.practice.domain.page_face import PaperPage
from backend.practice.domain.page_layout import alignment_marks, answer_box, placed_slot_lines, qr_origin
from backend.practice.domain.qr_code import encode_qr, qr_payload


class _FontMissing(Exception):
    """CJK text is on the page and no face opened."""


class StdPdf:
    """Write a PDF 1.4 document. Latin uses Helvetica. Chinese uses the system face."""

    def render(self, page: PaperPage) -> bytes | Err:
        return self.render_document((page,))

    def render_document(self, pages: Sequence[PaperPage]) -> bytes | Err:
        slotted = any(page.slots for page in pages)
        prepared: list[tuple[tuple[tuple[str, int, int], ...], list[str]]] = []
        for page in pages:
            try:
                if slotted:
                    prepared.append((_slot_lines(page), _slot_graphics(page)))
                else:
                    prepared.append((_legacy_positions(_lines(page)), _graphics(page)))
            except (ValueError, RuntimeError):
                return Err("not_rendered", "this synthetic page cannot encode the formula")
        try:
            if any(_has_cjk(text) for lines, _ in prepared for text, _x, _y in lines):
                return _pdf_cjk(prepared)
            encoded = [
                tuple((_pdf_text(text), x, y) for text, x, y in lines) for lines, _ in prepared
            ]
            marks = [graphics for _, graphics in prepared]
            return _pdf(encoded, marks)
        except _FontMissing:
            return Err("pdf_font_missing", MISSING_FONT)
        except UnicodeEncodeError:
            return Err("not_rendered", "this synthetic page cannot encode the formula")


def _lines(page: PaperPage) -> tuple[str, ...]:
    """Legacy face. The formula is the only question text. Slots use _slot_lines."""
    lines: list[str] = []
    if page.printed_external_id:
        lines.append(page.printed_external_id)
    lines.append("page " + str(page.page_number))
    lines.append("pages " + str(page.page_count))
    if page.formula:
        lines.append("formula " + page.formula)
    return tuple(lines)


def _legacy_positions(lines: tuple[str, ...]) -> tuple[tuple[str, int, int], ...]:
    y = 780
    placed: list[tuple[str, int, int]] = []
    for line in lines:
        placed.append((line, 48, y))
        y -= 18
    return tuple(placed)


def _slot_lines(page: PaperPage) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = list(_legacy_positions(_header(page)))
    for slot in page.slots:
        rows.extend(
            placed_slot_lines(slot.order_no, slot.slot_no, slot.slot_span, slot.stem, slot.options)
        )
    return tuple(rows)


def _header(page: PaperPage) -> tuple[str, ...]:
    lines: list[str] = []
    if page.printed_external_id:
        lines.append(page.printed_external_id)
    lines.append("page " + str(page.page_number))
    lines.append("pages " + str(page.page_count))
    return tuple(lines)


def _graphics(page: PaperPage) -> list[str]:
    commands = _marks()
    left, bottom, width, height = answer_box(max(page.page_number, 1))
    commands.append(f"{left} {bottom} {width} {height} re S")
    commands.extend(_qr(page))
    return commands


def _slot_graphics(page: PaperPage) -> list[str]:
    commands = _marks()
    for slot in page.slots:
        left, bottom, width, height = slot.answer_box
        commands.append(f"{left} {bottom} {width} {height} re S")
    commands.extend(_qr(page))
    return commands


def _marks() -> list[str]:
    commands = ["0 0 0 rg", "0 0 0 RG", "1.5 w"]
    for left, bottom, width, height in alignment_marks():
        commands.append(f"{left} {bottom} {width} {height} re f")
    return commands


def _qr(page: PaperPage) -> list[str]:
    if not page.qr_printed:
        return []
    matrix = encode_qr(qr_payload(page.paper_id, page.page_number))
    origin_x, origin_y, module = qr_origin()
    size = len(matrix)
    commands: list[str] = []
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


def _pdf(pages: list[tuple[tuple[str, int, int], ...]], graphics: list[list[str]]) -> bytes:
    contents = [_latin_stream(lines, marks) for lines, marks in zip(pages, graphics)]
    font_at = 3 + 2 * len(contents)
    resources = f"<< /Font << /F1 {font_at} 0 R >> >>".encode("ascii")
    trailing = [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    return _assemble(contents, resources, trailing)


def _latin_stream(lines: tuple[tuple[str, int, int], ...], graphics: list[str]) -> bytes:
    commands = list(graphics)
    commands.extend(["BT", "/F1 12 Tf"])
    for line, x, y in lines:
        commands.append(f"1 0 0 1 {x} {y} Tm ({line}) Tj")
    commands.append("ET")
    return ("\n".join(commands) + "\n").encode("latin-1")


def _pdf_cjk(prepared: list[tuple[tuple[tuple[str, int, int], ...], list[str]]]) -> bytes:
    codes: set[int] = set()
    for lines, _ in prepared:
        for line, _x, _y in lines:
            for char in line:
                if _is_cjk(char):
                    codes.add(ord(char))
                else:
                    _pdf_text(char)
    face = load_system_face()
    if face is None:
        raise _FontMissing()
    font = subset_page_font(face, codes)
    if font is None:
        raise UnicodeEncodeError("cp1252", "cjk", 0, 1, "glyph missing")
    contents = [_cjk_stream(lines, marks, font) for lines, marks in prepared]
    font_at = 3 + 2 * len(contents)
    resources = f"<< /Font << /F1 {font_at} 0 R /F2 {font_at + 1} 0 R >> >>".encode("ascii")
    return _assemble(contents, resources, _cjk_fonts(font, codes, font_at))


def _cjk_stream(
    lines: tuple[tuple[str, int, int], ...], graphics: list[str], font: PageFont
) -> bytes:
    commands = list(graphics)
    commands.append("BT")
    for line, x, y in lines:
        commands.append(f"1 0 0 1 {x} {y} Tm")
        for kind, run in _runs(line):
            if kind == "cjk":
                glyphs = "".join(f"{font.glyph_id[ord(char)]:04X}" for char in run)
                commands.append(f"/F2 12 Tf <{glyphs}> Tj")
            else:
                commands.append(f"/F1 12 Tf ({_pdf_text(run)}) Tj")
    commands.append("ET")
    return ("\n".join(commands) + "\n").encode("latin-1")


def _cjk_fonts(font: PageFont, codes: set[int], font_at: int) -> list[bytes]:
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
        _cid_font(font, font_at, widths),
        _font_descriptor(font, font_at),
        _font_program(font),
        _stream(unicode_map),
    ]


def _cid_font(font: PageFont, font_at: int, widths: str) -> bytes:
    if font.kind == "cff":
        subtype = "CIDFontType0"
        identity = ""
    else:
        subtype = "CIDFontType2"
        identity = " /CIDToGIDMap /Identity"
    return (
        f"<< /Type /Font /Subtype /{subtype} /BaseFont /K12QBK+{font.name} "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {font_at + 3} 0 R{identity} /W [{widths}] >>"
    ).encode("ascii")


def _font_descriptor(font: PageFont, font_at: int) -> bytes:
    x0, y0, x1, y1 = font.bbox
    file_key = "FontFile3" if font.kind == "cff" else "FontFile2"
    return (
        f"<< /Type /FontDescriptor /FontName /K12QBK+{font.name} /Flags 4 "
        f"/FontBBox [{x0} {y0} {x1} {y1}] /ItalicAngle 0 "
        f"/Ascent {font.ascent} /Descent {font.descent} /CapHeight {font.ascent} "
        f"/StemV 80 /{file_key} {font_at + 4} 0 R >>"
    ).encode("ascii")


def _font_program(font: PageFont) -> bytes:
    payload = font.ttf
    if font.kind != "cff":
        return _stream(payload, length1=True)
    header = f"<< /Length {len(payload)} /Subtype /CIDFontType0C >>\nstream\n".encode("ascii")
    return header + payload + b"\nendstream"


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
