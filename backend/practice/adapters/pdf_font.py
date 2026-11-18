"""Subset the installed KaiTi face for one PDF page.

The font file stays in the Windows Fonts folder. This module reads simkai.ttf,
then Microsoft YaHei, then SimHei, and returns only the glyphs this page uses.
It does not copy the font into the repository.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

_FACES = (
    ("simkai.ttf", "KaiTi"),
    ("msyh.ttc", "MicrosoftYaHei"),
    ("simhei.ttf", "SimHei"),
)


@dataclass(frozen=True)
class SystemFace:
    """One installed face. data is the whole file; origin is the sfnt offset."""

    name: str
    data: bytes
    origin: int


@dataclass(frozen=True)
class PageFont:
    """A subset whose glyph ids are safe to draw with Identity-H."""

    name: str
    ttf: bytes
    glyph_id: dict[int, int]
    width: dict[int, int]
    bbox: tuple[int, int, int, int]
    ascent: int
    descent: int


def load_system_face() -> SystemFace | None:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    folder = (Path(windir) / "Fonts").resolve()
    if not folder.is_dir():
        return None
    for filename, name in _FACES:
        path = (folder / filename).resolve()
        if path.parent != folder or not path.is_file():
            continue
        data = path.read_bytes()
        origin = _face_origin(data)
        if origin is None:
            continue
        return SystemFace(name, data, origin)
    return None


def subset_page_font(face: SystemFace, codes: set[int]) -> PageFont | None:
    if not codes:
        return None
    tables = _tables(face.data, face.origin)
    if tables is None:
        return None
    needed = {0}
    mapping: dict[int, int] = {}
    for code in codes:
        gid = _cmap_gid(tables, code)
        if gid <= 0:
            return None
        _collect(tables, gid, needed)
        mapping[code] = gid
    order = [0, *[gid for gid in sorted(needed) if gid != 0]]
    new_of = {old: index for index, old in enumerate(order)}
    glyf, loca = _subset_glyf(tables, order, new_of)
    if glyf is None or loca is None:
        return None
    upem, bbox = _head_metrics(tables)
    widths = {
        code: round(_advance(tables, old) * 1000 / upem) for code, old in mapping.items()
    }
    ascent = round(struct.unpack_from(">h", tables[b"hhea"], 4)[0] * 1000 / upem)
    descent = round(struct.unpack_from(">h", tables[b"hhea"], 6)[0] * 1000 / upem)
    built = _build_ttf(tables, glyf, loca, new_of, mapping)
    if built is None:
        return None
    return PageFont(
        face.name,
        built,
        {code: new_of[old] for code, old in mapping.items()},
        widths,
        bbox,
        ascent,
        descent,
    )


def _face_origin(data: bytes) -> int | None:
    if data[:4] == b"\x00\x01\x00\x00":
        return 0
    if data[:4] != b"ttcf" or len(data) < 16:
        return None
    count = struct.unpack_from(">I", data, 8)[0]
    if count < 1:
        return None
    return struct.unpack_from(">I", data, 12)[0]


def _tables(data: bytes, origin: int) -> dict[bytes, bytes] | None:
    if origin + 12 > len(data):
        return None
    count = struct.unpack_from(">H", data, origin + 4)[0]
    found: dict[bytes, bytes] = {}
    for index in range(count):
        slot = origin + 12 + index * 16
        if slot + 16 > len(data):
            return None
        tag, _checksum, start, length = struct.unpack_from(">4sIII", data, slot)
        if start + length > len(data):
            return None
        found[tag] = data[start : start + length]
    required = (b"cmap", b"glyf", b"head", b"hhea", b"hmtx", b"loca", b"maxp")
    if any(tag not in found for tag in required):
        return None
    return found


def _cmap_gid(tables: dict[bytes, bytes], code: int) -> int:
    cmap = tables[b"cmap"]
    if len(cmap) < 4:
        return 0
    count = struct.unpack_from(">H", cmap, 2)[0]
    for index in range(count):
        slot = 4 + index * 8
        if slot + 8 > len(cmap):
            return 0
        _platform, _encoding, offset = struct.unpack_from(">HHI", cmap, slot)
        gid = _gid_at(cmap, offset, code)
        if gid > 0:
            return gid
    return 0


def _gid_at(cmap: bytes, offset: int, code: int) -> int:
    if offset + 2 > len(cmap):
        return 0
    fmt = struct.unpack_from(">H", cmap, offset)[0]
    if fmt == 4:
        return _gid_format4(cmap, offset, code)
    if fmt == 12:
        return _gid_format12(cmap, offset, code)
    return 0


def _gid_format4(cmap: bytes, offset: int, code: int) -> int:
    if offset + 14 > len(cmap):
        return 0
    seg_count = struct.unpack_from(">H", cmap, offset + 6)[0] // 2
    end_at = offset + 14
    start_at = end_at + seg_count * 2 + 2
    delta_at = start_at + seg_count * 2
    range_at = delta_at + seg_count * 2
    if range_at + seg_count * 2 > len(cmap):
        return 0
    for index in range(seg_count):
        end = struct.unpack_from(">H", cmap, end_at + index * 2)[0]
        if code > end:
            continue
        start = struct.unpack_from(">H", cmap, start_at + index * 2)[0]
        if code < start:
            return 0
        delta = struct.unpack_from(">H", cmap, delta_at + index * 2)[0]
        range_offset = struct.unpack_from(">H", cmap, range_at + index * 2)[0]
        if range_offset == 0:
            return (code + delta) & 0xFFFF
        pos = range_at + index * 2 + range_offset + 2 * (code - start)
        if pos + 2 > len(cmap):
            return 0
        glyph = struct.unpack_from(">H", cmap, pos)[0]
        if glyph == 0:
            return 0
        return (glyph + delta) & 0xFFFF
    return 0


def _gid_format12(cmap: bytes, offset: int, code: int) -> int:
    if offset + 16 > len(cmap):
        return 0
    groups = struct.unpack_from(">I", cmap, offset + 12)[0]
    for index in range(groups):
        slot = offset + 16 + index * 12
        if slot + 12 > len(cmap):
            return 0
        start, end, first = struct.unpack_from(">III", cmap, slot)
        if start <= code <= end:
            return first + (code - start)
    return 0


def _glyph_count(tables: dict[bytes, bytes]) -> int:
    maxp = tables[b"maxp"]
    if len(maxp) < 6:
        return 0
    return struct.unpack_from(">H", maxp, 4)[0]


def _loca(tables: dict[bytes, bytes], gid: int) -> int:
    head = tables[b"head"]
    loca = tables[b"loca"]
    short = struct.unpack_from(">h", head, 50)[0] == 0
    if short:
        return struct.unpack_from(">H", loca, gid * 2)[0] * 2
    return struct.unpack_from(">I", loca, gid * 4)[0]


def _glyph(tables: dict[bytes, bytes], gid: int) -> bytes:
    glyf = tables[b"glyf"]
    start = _loca(tables, gid)
    end = _loca(tables, gid + 1)
    return glyf[start:end]


def _collect(tables: dict[bytes, bytes], gid: int, found: set[int]) -> None:
    if gid in found or gid >= _glyph_count(tables):
        return
    found.add(gid)
    raw = _glyph(tables, gid)
    if len(raw) < 10 or struct.unpack_from(">h", raw, 0)[0] >= 0:
        return
    pos = 10
    while pos + 4 <= len(raw):
        flags, component = struct.unpack_from(">HH", raw, pos)
        _collect(tables, component, found)
        pos += 4
        pos += 4 if flags & 1 else 2
        if flags & 8:
            pos += 2
        elif flags & 64:
            pos += 4
        elif flags & 128:
            pos += 8
        if not flags & 32:
            break


def _subset_glyf(
    tables: dict[bytes, bytes], order: list[int], new_of: dict[int, int]
) -> tuple[bytes, bytes] | tuple[None, None]:
    parts: list[bytes] = []
    offsets = [0]
    for old in order:
        raw = _rewrite(_glyph(tables, old), new_of)
        if len(raw) % 4:
            raw += b"\x00" * (4 - len(raw) % 4)
        parts.append(raw)
        offsets.append(offsets[-1] + len(raw))
    loca = b"".join(struct.pack(">I", offset) for offset in offsets)
    return b"".join(parts), loca


def _rewrite(glyph: bytes, new_of: dict[int, int]) -> bytes:
    if len(glyph) < 10 or struct.unpack_from(">h", glyph, 0)[0] >= 0:
        return glyph
    out = bytearray(glyph)
    pos = 10
    while pos + 4 <= len(out):
        flags, component = struct.unpack_from(">HH", out, pos)
        struct.pack_into(">H", out, pos + 2, new_of.get(component, 0))
        pos += 4
        pos += 4 if flags & 1 else 2
        if flags & 8:
            pos += 2
        elif flags & 64:
            pos += 4
        elif flags & 128:
            pos += 8
        if not flags & 32:
            break
    return bytes(out)


def _advance(tables: dict[bytes, bytes], gid: int) -> int:
    hhea = tables[b"hhea"]
    hmtx = tables[b"hmtx"]
    count = struct.unpack_from(">H", hhea, 34)[0]
    if gid < count:
        return struct.unpack_from(">H", hmtx, gid * 4)[0]
    return struct.unpack_from(">H", hmtx, (count - 1) * 4)[0]


def _head_metrics(tables: dict[bytes, bytes]) -> tuple[int, tuple[int, int, int, int]]:
    head = tables[b"head"]
    upem = struct.unpack_from(">H", head, 18)[0] or 1000
    box = struct.unpack_from(">hhhh", head, 36)
    scale = 1000 / upem
    return upem, tuple(round(value * scale) for value in box)  # type: ignore[return-value]


def _build_ttf(
    tables: dict[bytes, bytes],
    glyf: bytes,
    loca: bytes,
    new_of: dict[int, int],
    mapping: dict[int, int],
) -> bytes | None:
    count = len(new_of)
    head = bytearray(tables[b"head"][:54])
    struct.pack_into(">H", head, 50, 1)
    struct.pack_into(">I", head, 8, 0)
    hhea = bytearray(tables[b"hhea"][:36])
    advances = [_advance(tables, old) for old in sorted(new_of, key=new_of.get)]
    struct.pack_into(">H", hhea, 10, max(advances) if advances else 0)
    struct.pack_into(">H", hhea, 34, count)
    hmtx = b"".join(
        struct.pack(">Hh", _advance(tables, old), _lsb(tables, old))
        for old in sorted(new_of, key=new_of.get)
    )
    maxp = bytearray(tables[b"maxp"][:32] if len(tables[b"maxp"]) >= 32 else tables[b"maxp"])
    if len(maxp) >= 6:
        struct.pack_into(">H", maxp, 4, count)
    pieces = {
        b"cmap": _cmap(mapping, new_of),
        b"glyf": glyf,
        b"head": bytes(head),
        b"hhea": bytes(hhea),
        b"hmtx": hmtx,
        b"loca": loca,
        b"maxp": bytes(maxp),
        b"name": tables.get(b"name", _name()),
        b"OS/2": tables.get(b"OS/2", b""),
        b"post": struct.pack(">iihhIIIII", 0x00030000, 0, 0, 0, 0, 0, 0, 0, 0),
    }
    if not pieces[b"OS/2"]:
        del pieces[b"OS/2"]
    return _pack(pieces)


def _lsb(tables: dict[bytes, bytes], gid: int) -> int:
    hhea = tables[b"hhea"]
    hmtx = tables[b"hmtx"]
    count = struct.unpack_from(">H", hhea, 34)[0]
    if gid < count:
        return struct.unpack_from(">h", hmtx, gid * 4 + 2)[0]
    return struct.unpack_from(">h", hmtx, count * 4 + (gid - count) * 2)[0]


def _cmap(mapping: dict[int, int], new_of: dict[int, int]) -> bytes:
    pairs = sorted((code, new_of[old]) for code, old in mapping.items())
    segments = [(code, code, glyph) for code, glyph in pairs]
    segments.append((0xFFFF, 0xFFFF, 0))
    seg_count = len(segments)
    entry = seg_count.bit_length() - 1
    search = 2 * (1 << entry)
    body = struct.pack(
        ">HHHHHH",
        4,
        16 + seg_count * 8,
        0,
        seg_count * 2,
        search,
        entry,
    )
    body += struct.pack(">H", seg_count * 2 - search)
    body += struct.pack(">" + "H" * seg_count, *[end for _start, end, _gid in segments])
    body += struct.pack(">H", 0)
    body += struct.pack(">" + "H" * seg_count, *[start for start, _end, _gid in segments])
    deltas = [((0 if end == 0xFFFF else glyph) - start) & 0xFFFF for start, end, glyph in segments]
    body += struct.pack(">" + "H" * seg_count, *deltas)
    body += struct.pack(">" + "H" * seg_count, *([0] * seg_count))
    record = struct.pack(">HHI", 3, 1, 12)
    return struct.pack(">HH", 0, 1) + record + body


def _name() -> bytes:
    text = "KaiTi".encode("utf-16be")
    # nameID 1, platform 3, one record. Offset 6 + 12 = 18.
    record = struct.pack(">HHHHHH", 3, 1, 0x409, 1, len(text), 0)
    return struct.pack(">HHH", 0, 1, 18) + record + text


def _pack(pieces: dict[bytes, bytes]) -> bytes:
    tags = sorted(pieces)
    count = len(tags)
    entry = count.bit_length() - 1
    search = 16 * (1 << entry)
    header = struct.pack(">IHHHH", 0x00010000, count, search, entry, count * 16 - search)
    directory = bytearray(count * 16)
    body = bytearray()
    start = 12 + count * 16
    stored: list[tuple[bytes, int, int]] = []
    for tag in tags:
        raw = pieces[tag]
        padded = raw + b"\x00" * ((4 - len(raw) % 4) % 4)
        stored.append((tag, len(body) + start, len(raw)))
        body += padded
    font = bytearray(header)
    font += directory
    font += body
    for index, (tag, offset, length) in enumerate(stored):
        raw = pieces[tag]
        slot = 12 + index * 16
        struct.pack_into(">4sIII", font, slot, tag, _checksum(raw), offset, length)
    total = _checksum(bytes(font))
    adjust = (0xB1B0AFBA - total) & 0xFFFFFFFF
    head_offset = next(offset for tag, offset, _length in stored if tag == b"head")
    struct.pack_into(">I", font, head_offset + 8, adjust)
    return bytes(font)


def _checksum(data: bytes) -> int:
    padded = data + b"\x00" * ((4 - len(data) % 4) % 4)
    total = 0
    for index in range(0, len(padded), 4):
        total = (total + struct.unpack_from(">I", padded, index)[0]) & 0xFFFFFFFF
    return total
