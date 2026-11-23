"""Subset a CID-keyed CFF face down to the glyphs one page draws.

CharStrings are copied unchanged. Local subroutines stay at their original
indexes, so callsubr operands are not rewritten. A local subroutine this page
does not reach becomes a single return. Global subroutines are kept whole.
A failed walk keeps that font dict's local subroutines whole instead of
emitting a program that would draw the wrong outline.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from backend.practice.adapters.pdf_font import (
    PageFont,
    SystemFace,
    _advance,
    _cmap_gid,
    _head_metrics,
)

_Operand = int | bytes
_Op = int | tuple[int, int]
_Entry = tuple[_Op, list[_Operand]]


@dataclass(frozen=True)
class _FacePart:
    font: list[_Entry]
    private: list[_Entry]
    subrs: tuple[tuple[int, int], ...]
    subr_raw: bytes


def subset_cff(face: SystemFace, tables: dict[bytes, bytes], codes: set[int]) -> PageFont | None:
    """Return a CID subset, or None when this face cannot draw every code."""
    try:
        built, glyph_id, widths = _build(tables, codes, f"K12QBK+{face.name}")
    except (ValueError, IndexError, struct.error, OverflowError, KeyError):
        return None
    if built is None:
        return None
    _upem, bbox = _head_metrics(tables)
    hhea = tables[b"hhea"]
    ascent = round(struct.unpack_from(">h", hhea, 4)[0] * 1000 / _upem)
    descent = round(struct.unpack_from(">h", hhea, 6)[0] * 1000 / _upem)
    return PageFont(face.name, built, glyph_id, widths, bbox, ascent, descent, kind="cff")


def _build(
    tables: dict[bytes, bytes], codes: set[int], font_name: str
) -> tuple[bytes | None, dict[int, int], dict[int, int]]:
    cff = tables[b"CFF "]
    header, _name_raw, top, string_raw, gsubr_raw = _preamble(cff)
    name_raw = _cff_name(font_name)
    char_spans, _end = _index_spans(cff, _only_int(top, 17))
    count = len(char_spans)
    cids = _charset(cff, _only_int(top, 15), count)
    parts = _face_parts(cff, _only_int(top, (12, 36)))
    fdselect_at = _only_int(top, (12, 37))
    order, mapping = _order(tables, codes, count, cids)
    if order is None or mapping is None:
        return None, {}, {}
    originals = [cff[start:end] for start, end in (char_spans[gid] for gid in order)]
    keep, used = _used_subrs(cff, order, parts, char_spans, fdselect_at, count)
    regions = [_region(cff, part, index, keep, used) for index, part in enumerate(parts)]
    charset = _charset_bytes([cids[gid] for gid in order])
    chosen = [_fd_of(cff, fdselect_at, gid, count) for gid in order]
    chars = _build_index(originals)
    built = _assemble(
        header,
        name_raw,
        top,
        string_raw,
        gsubr_raw,
        charset,
        bytes([0, *chosen]),
        chars,
        parts,
        regions,
    )
    _check_roundtrip(built, originals)
    widths = _widths(tables, mapping)
    return built, {code: cids[gid] for code, gid in mapping.items()}, widths


def _cff_name(name: str) -> bytes:
    raw = name.encode("ascii")
    if not raw or len(raw) > 127:
        raise ValueError("font name")
    return struct.pack(">HB", 1, 1) + bytes((1, 1 + len(raw))) + raw


def _preamble(cff: bytes) -> tuple[bytes, bytes, list[_Entry], bytes, bytes]:
    if len(cff) < 4 or cff[0] != 1:
        raise ValueError("cff header")
    hdr = cff[2]
    if hdr < 4 or hdr > 64 or hdr > len(cff):
        raise ValueError("hdrSize")
    pos = hdr
    name_at = pos
    name_spans, pos = _index_spans(cff, pos)
    if not name_spans:
        raise ValueError("name")
    name_raw = cff[name_at:pos]
    top_spans, pos = _index_spans(cff, pos)
    if len(top_spans) != 1:
        raise ValueError("top")
    top = _parse_dict(cff[top_spans[0][0] : top_spans[0][1]])
    if _operands(top, 18) is not None:
        raise ValueError("top private")
    string_at = pos
    _spans, pos = _index_spans(cff, pos)
    string_raw = cff[string_at:pos]
    gsubr_at = pos
    _spans, pos = _index_spans(cff, pos)
    return cff[:hdr], name_raw, top, string_raw, cff[gsubr_at:pos]


def _order(
    tables: dict[bytes, bytes], codes: set[int], count: int, cids: list[int]
) -> tuple[list[int] | None, dict[int, int] | None]:
    mapping: dict[int, int] = {}
    needed = {0}
    for code in codes:
        gid = _cmap_gid(tables, code)
        if gid <= 0 or gid >= count or cids[gid] <= 0:
            return None, None
        mapping[code] = gid
        needed.add(gid)
    return sorted(needed), mapping


def _widths(tables: dict[bytes, bytes], mapping: dict[int, int]) -> dict[int, int]:
    upem, _box = _head_metrics(tables)
    return {code: round(_advance(tables, gid) * 1000 / upem) for code, gid in mapping.items()}


def _face_parts(cff: bytes, fdarray_at: int) -> list[_FacePart]:
    spans, _end = _index_spans(cff, fdarray_at)
    parts: list[_FacePart] = []
    for start, end in spans:
        font = _parse_dict(cff[start:end])
        private_op = _operands(font, 18)
        if private_op is None or len(private_op) < 2:
            raise ValueError("fd private")
        size = _as_int(private_op[-2])
        offset = _as_int(private_op[-1])
        if size < 0 or offset < 0 or offset + size > len(cff):
            raise ValueError("private range")
        private = _parse_dict(cff[offset : offset + size])
        subr_op = _operands(private, 19)
        if subr_op is None:
            parts.append(_FacePart(font, private, (), b""))
            continue
        subr_at = offset + _as_int(subr_op[-1])
        subr_spans, subr_end = _index_spans(cff, subr_at)
        parts.append(_FacePart(font, private, tuple(subr_spans), cff[subr_at:subr_end]))
    if not parts:
        raise ValueError("fdarray")
    return parts


def _used_subrs(
    cff: bytes,
    order: list[int],
    parts: list[_FacePart],
    char_spans: list[tuple[int, int]],
    fdselect_at: int,
    count: int,
) -> tuple[set[int], dict[int, set[int]]]:
    keep: set[int] = set()
    used: dict[int, set[int]] = {}
    for gid in order:
        fd = _fd_of(cff, fdselect_at, gid, count)
        if fd in keep:
            continue
        start, end = char_spans[gid]
        found = _closure(cff[start:end], parts[fd].subrs, cff)
        if found is None:
            if not parts[fd].subr_raw:
                raise ValueError("unresolved subr")
            keep.add(fd)
            used.pop(fd, None)
            continue
        used.setdefault(fd, set()).update(found)
    return keep, used


def _closure(blob: bytes, spans: tuple[tuple[int, int], ...], cff: bytes) -> set[int] | None:
    """Local subroutine indexes reached from blob. None means keep them all."""
    found: set[int] = set()
    shift = _bias(len(spans))

    def walk(data: bytes) -> bool:
        calls, ok = _local_calls(data)
        if not ok:
            return False
        for value in calls:
            index = value + shift
            if index < 0 or index >= len(spans):
                return False
            if index in found:
                continue
            found.add(index)
            start, end = spans[index]
            if not walk(cff[start:end]):
                return False
        return True

    if not walk(blob):
        return None
    return found


def _region(
    cff: bytes, part: _FacePart, index: int, keep: set[int], used: dict[int, set[int]]
) -> tuple[bytes, int]:
    """Return the private dict plus any local subroutines, and the dict size."""
    if index in keep and part.subr_raw:
        private = _private_dict(part.private, True)
        return private + part.subr_raw, len(private)
    wanted = used.get(index, set())
    if wanted and part.subrs:
        blobs = [
            cff[start:end] if slot in wanted else b"\x0b"
            for slot, (start, end) in enumerate(part.subrs)
        ]
        private = _private_dict(part.private, True)
        return private + _build_index(blobs), len(private)
    private = _private_dict(part.private, False)
    return private, len(private)


def _assemble(
    header: bytes,
    name_raw: bytes,
    top: list[_Entry],
    string_raw: bytes,
    gsubr_raw: bytes,
    charset: bytes,
    fdselect: bytes,
    chars: bytes,
    parts: list[_FacePart],
    regions: list[tuple[bytes, int]],
) -> bytes:
    bodies = [body for body, _size in regions]
    sizes = [size for _body, size in regions]
    font_dicts = [_font_dict(part.font, sizes[index], 0) for index, part in enumerate(parts)]
    top_len = _index_len([_encode(_shifted_top(top, 0, 0, 0, 0))])
    fdarray_len = _index_len(font_dicts)
    prefix_len = (
        len(header)
        + len(name_raw)
        + top_len
        + len(string_raw)
        + len(gsubr_raw)
        + len(charset)
        + len(fdselect)
        + len(chars)
        + fdarray_len
    )
    cursor = prefix_len
    offsets: list[int] = []
    for body in bodies:
        offsets.append(cursor)
        cursor += len(body)
    font_dicts = [
        _font_dict(part.font, sizes[index], offsets[index]) for index, part in enumerate(parts)
    ]
    if _index_len(font_dicts) != fdarray_len:
        raise ValueError("fdarray size")
    charset_at = len(header) + len(name_raw) + top_len + len(string_raw) + len(gsubr_raw)
    fdselect_at = charset_at + len(charset)
    chars_at = fdselect_at + len(fdselect)
    fdarray_at = chars_at + len(chars)
    top_index = _build_index(
        [_encode(_shifted_top(top, charset_at, chars_at, fdarray_at, fdselect_at))]
    )
    if len(top_index) != top_len:
        raise ValueError("top size")
    return b"".join(
        [
            header,
            name_raw,
            top_index,
            string_raw,
            gsubr_raw,
            charset,
            fdselect,
            chars,
            _build_index(font_dicts),
            *bodies,
        ]
    )


def _check_roundtrip(built: bytes, originals: list[bytes]) -> None:
    _header, _name, top, _string, _gsubr = _preamble(built)
    spans, _end = _index_spans(built, _only_int(top, 17))
    if len(spans) != len(originals):
        raise ValueError("glyph count")
    for index, original in enumerate(originals):
        start, end = spans[index]
        if built[start:end] != original:
            raise ValueError("charstring changed")


def _shifted_top(
    top: list[_Entry], charset_at: int, chars_at: int, fdarray_at: int, fdselect_at: int
) -> list[_Entry]:
    updates: dict[_Op, list[_Operand]] = {
        15: [charset_at],
        17: [chars_at],
        (12, 36): [fdarray_at],
        (12, 37): [fdselect_at],
    }
    shifted: list[_Entry] = []
    seen: set[_Op] = set()
    for op, operands in top:
        if op == 16:
            continue
        if op in updates:
            shifted.append((op, updates[op]))
            seen.add(op)
        else:
            shifted.append((op, list(operands)))
    missing = [op for op in updates if op not in seen]
    if missing:
        raise ValueError("top offset")
    return shifted


def _font_dict(entries: list[_Entry], size: int, offset: int) -> bytes:
    encoded: list[_Entry] = []
    seen = False
    for op, operands in entries:
        if op == 18:
            encoded.append((18, [size, offset]))
            seen = True
        else:
            encoded.append((op, list(operands)))
    if not seen:
        raise ValueError("font dict")
    return _encode(encoded)


def _private_dict(entries: list[_Entry], include_subrs: bool) -> bytes:
    body: list[_Entry] = [(op, list(operands)) for op, operands in entries if op != 19]
    encoded = _encode(body)
    if not include_subrs:
        return encoded or (_enc_int(0) + b"\x14")
    relative = len(encoded) + 6
    full = encoded + _enc_int(relative) + b"\x13"
    if len(full) != relative:
        raise ValueError("subrs offset")
    return full


def _charset_bytes(cids: list[int]) -> bytes:
    out = bytearray([0])
    for cid in cids[1:]:
        if not 0 < cid <= 0xFFFF:
            raise ValueError("cid")
        out += struct.pack(">H", cid)
    return bytes(out)


def _charset(cff: bytes, offset: int, count: int) -> list[int]:
    if offset < 0 or offset >= len(cff) or count < 1:
        raise ValueError("charset")
    fmt = cff[offset]
    cids = [0] * count
    gid = 1
    pos = offset + 1
    if fmt == 0:
        for gid in range(1, count):
            cids[gid] = struct.unpack_from(">H", cff, pos)[0]
            pos += 2
        return cids
    while gid < count:
        if fmt == 1:
            first = struct.unpack_from(">H", cff, pos)[0]
            n_left = cff[pos + 2]
            pos += 3
        elif fmt == 2:
            first, n_left = struct.unpack_from(">HH", cff, pos)
            pos += 4
        else:
            raise ValueError("charset format")
        for step in range(n_left + 1):
            if gid >= count:
                break
            cids[gid] = first + step
            gid += 1
    if gid != count:
        raise ValueError("charset cover")
    return cids


def _fd_of(cff: bytes, offset: int, gid: int, count: int) -> int:
    if offset < 0 or offset >= len(cff) or not 0 <= gid < count:
        raise ValueError("fdselect")
    fmt = cff[offset]
    if fmt == 0:
        slot = offset + 1 + gid
        if slot >= len(cff):
            raise ValueError("fdselect")
        return cff[slot]
    if fmt != 3:
        raise ValueError("fdselect format")
    ranges = struct.unpack_from(">H", cff, offset + 1)[0]
    pos = offset + 3
    for _index in range(ranges):
        first = struct.unpack_from(">H", cff, pos)[0]
        fd = cff[pos + 2]
        nxt = struct.unpack_from(">H", cff, pos + 3)[0]
        if first <= gid < nxt:
            return fd
        pos += 3
    raise ValueError("fdselect gid")


def _local_calls(blob: bytes) -> tuple[list[int], bool]:
    """Biased local subroutine numbers. Byte 29 is callgsubr, not an integer."""
    stack: list[int] = []
    hints = 0
    calls: list[int] = []
    index = 0
    while index < len(blob):
        byte = blob[index]
        if byte == 28:
            if index + 3 > len(blob):
                return calls, False
            stack.append(struct.unpack_from(">h", blob, index + 1)[0])
            index += 3
            continue
        if byte == 255:
            if index + 5 > len(blob):
                return calls, False
            stack.append(0)
            index += 5
            continue
        if 247 <= byte <= 250:
            if index + 2 > len(blob):
                return calls, False
            stack.append((byte - 247) * 256 + blob[index + 1] + 108)
            index += 2
            continue
        if 251 <= byte <= 254:
            if index + 2 > len(blob):
                return calls, False
            stack.append(-(byte - 251) * 256 - blob[index + 1] - 108)
            index += 2
            continue
        if 32 <= byte <= 246:
            stack.append(byte - 139)
            index += 1
            continue
        if byte == 12:
            if index + 2 > len(blob):
                return calls, False
            index += 2
            stack.clear()
            continue
        index += 1
        if byte in (1, 3, 18, 23):
            hints += len(stack) // 2
            stack.clear()
            continue
        if byte in (19, 20):
            if stack:
                hints += len(stack) // 2
                stack.clear()
            index += (hints + 7) // 8
            if index > len(blob):
                return calls, False
            continue
        if byte == 10:
            if not stack:
                return calls, False
            calls.append(stack[-1])
        elif byte == 29 and not stack:
            return calls, False
        stack.clear()
    return calls, index == len(blob)


def _bias(count: int) -> int:
    if count < 1240:
        return 107
    if count < 33900:
        return 1131
    return 32768


def _index_spans(buf: bytes, pos: int) -> tuple[list[tuple[int, int]], int]:
    if pos < 0 or pos + 2 > len(buf):
        raise ValueError("index")
    count = struct.unpack_from(">H", buf, pos)[0]
    pos += 2
    if count == 0:
        return [], pos
    off_size = buf[pos]
    if off_size < 1 or off_size > 4:
        raise ValueError("offSize")
    pos += 1
    offsets = []
    for _index in range(count + 1):
        if pos + off_size > len(buf):
            raise ValueError("offset")
        offsets.append(int.from_bytes(buf[pos : pos + off_size], "big"))
        pos += off_size
    spans = []
    for index in range(count):
        start = pos + offsets[index] - 1
        end = pos + offsets[index + 1] - 1
        if start < 0 or end < start or end > len(buf):
            raise ValueError("span")
        spans.append((start, end))
    return spans, pos + offsets[-1] - 1


def _build_index(blobs: list[bytes]) -> bytes:
    if not blobs:
        return b"\x00\x00"
    offsets = [1]
    for blob in blobs:
        offsets.append(offsets[-1] + len(blob))
    off_size = _off_size(offsets[-1])
    out = bytearray(struct.pack(">H", len(blobs)))
    out.append(off_size)
    for offset in offsets:
        out += offset.to_bytes(off_size, "big")
    out.extend(b"".join(blobs))
    return bytes(out)


def _index_len(blobs: list[bytes]) -> int:
    return len(_build_index(blobs))


def _off_size(last: int) -> int:
    if last < 0x100:
        return 1
    if last < 0x10000:
        return 2
    if last < 0x1000000:
        return 3
    if last < 0x100000000:
        return 4
    raise ValueError("offset size")


def _parse_dict(data: bytes) -> list[_Entry]:
    entries: list[_Entry] = []
    operands: list[_Operand] = []
    index = 0
    while index < len(data):
        byte = data[index]
        if byte == 28:
            operands.append(struct.unpack_from(">h", data, index + 1)[0])
            index += 3
            continue
        if byte == 29:
            operands.append(struct.unpack_from(">i", data, index + 1)[0])
            index += 5
            continue
        if byte == 30:
            end = _real_end(data, index)
            operands.append(data[index:end])
            index = end
            continue
        if 32 <= byte <= 246:
            operands.append(byte - 139)
            index += 1
            continue
        if 247 <= byte <= 250:
            operands.append((byte - 247) * 256 + data[index + 1] + 108)
            index += 2
            continue
        if 251 <= byte <= 254:
            operands.append(-(byte - 251) * 256 - data[index + 1] - 108)
            index += 2
            continue
        if byte == 12:
            entries.append(((12, data[index + 1]), operands))
            operands = []
            index += 2
            continue
        entries.append((byte, operands))
        operands = []
        index += 1
    if operands:
        raise ValueError("dict tail")
    return entries


def _real_end(data: bytes, index: int) -> int:
    pos = index + 1
    while pos < len(data):
        byte = data[pos]
        pos += 1
        if (byte >> 4) == 0x0F or (byte & 0x0F) == 0x0F:
            return pos
    raise ValueError("real")


def _encode(entries: list[_Entry]) -> bytes:
    out = bytearray()
    for op, operands in entries:
        for operand in operands:
            if isinstance(operand, int):
                out += _enc_int(operand)
            else:
                out += operand
        if isinstance(op, tuple):
            out += bytes((12, op[1]))
        else:
            out.append(op)
    return bytes(out)


def _enc_int(value: int) -> bytes:
    return b"\x1d" + struct.pack(">i", value)


def _operands(entries: list[_Entry], op: _Op) -> list[_Operand] | None:
    for found, operands in entries:
        if found == op:
            return operands
    return None


def _only_int(entries: list[_Entry], op: _Op) -> int:
    operands = _operands(entries, op)
    if operands is None or not operands:
        raise ValueError("missing op")
    return _as_int(operands[-1])


def _as_int(operand: _Operand) -> int:
    if not isinstance(operand, int):
        raise ValueError("number")
    return operand
