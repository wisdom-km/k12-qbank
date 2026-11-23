"""Version 3, error-correction M, QR symbol. No third-party package.

The payload is an opaque paper id and a page number. Callers must not pass
a student number or a name. Modules are booleans. The PDF draws them as
rectangles, so the payload is not a literal string in the file.
"""

from __future__ import annotations

_SIZE = 29
_DATA_CODEWORDS = 44
_EC_CODEWORDS = 26
_REMAINDER_BITS = 7
_FORMAT_GENERATOR = 0b10100110111
_FORMAT_MASK = 0b101010000010010
_EXP = [0] * 512
_LOG = [0] * 256


def _init_field() -> None:
    if _EXP[0] == 1:
        return
    value = 1
    for index in range(255):
        _EXP[index] = value
        _LOG[value] = index
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for index in range(255, 512):
        _EXP[index] = _EXP[index - 255]


def _mul(left: int, right: int) -> int:
    if left == 0 or right == 0:
        return 0
    return _EXP[_LOG[left] + _LOG[right]]


def qr_payload(paper_id: str, page_number: int) -> str:
    """Opaque paper id, a hash mark, and the page number. Nothing else."""
    if page_number < 1:
        raise ValueError("page_number")
    text = paper_id + "#" + str(page_number)
    raw = text.encode("ascii")
    if len(raw) > 42:
        raise ValueError("payload")
    return text


def format_bits(mask: int = 0) -> int:
    """15 format bits for ECC M and the given mask, already XOR-masked."""
    data = mask & 0b111
    remainder = data << 10
    for shift in range(4, -1, -1):
        if remainder & (1 << (shift + 10)):
            remainder ^= _FORMAT_GENERATOR << shift
    return ((data << 10) | (remainder & 0x3FF)) ^ _FORMAT_MASK


def encode_qr(payload: str) -> tuple[tuple[bool, ...], ...]:
    """Return a 29 by 29 matrix. Row 0 is the top. True is a dark module."""
    _init_field()
    raw = payload.encode("ascii")
    bits = _byte_mode(raw)
    codewords = [_byte(bits, index) for index in range(0, _DATA_CODEWORDS * 8, 8)]
    codewords.extend(_ec(codewords, _EC_CODEWORDS))
    stream = _bits_of(codewords) + [False] * _REMAINDER_BITS
    modules, reserved = _function_patterns()
    _place(modules, reserved, stream)
    _mask(modules, reserved)
    _write_format(modules, format_bits(0))
    return tuple(tuple(row) for row in modules)


def _byte_mode(raw: bytes) -> list[bool]:
    bits: list[bool] = []
    _put(bits, 0b0100, 4)
    _put(bits, len(raw), 8)
    for byte in raw:
        _put(bits, byte, 8)
    capacity = _DATA_CODEWORDS * 8
    _put(bits, 0, min(4, capacity - len(bits)))
    while len(bits) % 8:
        bits.append(False)
    pad = 0xEC
    while len(bits) < capacity:
        _put(bits, pad, 8)
        pad = 0x11 if pad == 0xEC else 0xEC
    return bits


def _put(bits: list[bool], value: int, length: int) -> None:
    for shift in range(length - 1, -1, -1):
        bits.append(bool((value >> shift) & 1))


def _byte(bits: list[bool], start: int) -> int:
    value = 0
    for offset in range(8):
        value = (value << 1) | int(bits[start + offset])
    return value


def _bits_of(codewords: list[int]) -> list[bool]:
    bits: list[bool] = []
    for word in codewords:
        _put(bits, word, 8)
    return bits


def _ec(data: list[int], count: int) -> list[int]:
    generator = [1]
    for index in range(count):
        generator = _poly_mul(generator, [1, _EXP[index]])
    remainder = [0] * count
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = remainder[1:] + [0]
        if factor:
            for index in range(count):
                remainder[index] ^= _mul(generator[index + 1], factor)
    return remainder


def _poly_mul(left: list[int], right: list[int]) -> list[int]:
    out = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            out[i + j] ^= _mul(a, b)
    return out


def _function_patterns() -> tuple[list[list[bool]], list[list[bool]]]:
    modules = [[False] * _SIZE for _ in range(_SIZE)]
    reserved = [[False] * _SIZE for _ in range(_SIZE)]
    for row, col in ((0, 0), (0, _SIZE - 7), (_SIZE - 7, 0)):
        _finder(modules, reserved, row, col)
        _separator(modules, reserved, row, col)
    for index in range(8, _SIZE - 8):
        dark = index % 2 == 0
        _lock(modules, reserved, 6, index, dark)
        _lock(modules, reserved, index, 6, dark)
    for row, col in ((6, 22), (22, 6), (22, 22)):
        if reserved[row][col]:
            continue
        _alignment(modules, reserved, row, col)
    _lock(modules, reserved, 4 * 3 + 9, 8, True)
    for row, col in _format_positions():
        _lock(modules, reserved, row, col, False)
    return modules, reserved


def _lock(modules: list[list[bool]], reserved: list[list[bool]], row: int, col: int, dark: bool) -> None:
    modules[row][col] = dark
    reserved[row][col] = True


def _finder(modules: list[list[bool]], reserved: list[list[bool]], top: int, left: int) -> None:
    for row in range(7):
        for col in range(7):
            border = row in {0, 6} or col in {0, 6}
            core = 2 <= row <= 4 and 2 <= col <= 4
            _lock(modules, reserved, top + row, left + col, border or core)


def _separator(modules: list[list[bool]], reserved: list[list[bool]], top: int, left: int) -> None:
    for offset in range(8):
        row = top - 1 if top else 7
        col = left - 1 if left else 7
        if 0 <= row < _SIZE and 0 <= left + offset < _SIZE:
            _lock(modules, reserved, row, left + offset, False)
        if 0 <= col < _SIZE and 0 <= top + offset < _SIZE:
            _lock(modules, reserved, top + offset, col, False)


def _alignment(modules: list[list[bool]], reserved: list[list[bool]], center_row: int, center_col: int) -> None:
    for row in range(center_row - 2, center_row + 3):
        for col in range(center_col - 2, center_col + 3):
            edge = abs(row - center_row) == 2 or abs(col - center_col) == 2
            heart = row == center_row and col == center_col
            _lock(modules, reserved, row, col, edge or heart)


def _format_positions() -> tuple[tuple[int, int], ...]:
    # Bit 0 is the least significant bit of the masked format word.
    primary = (
        (0, 8),
        (1, 8),
        (2, 8),
        (3, 8),
        (4, 8),
        (5, 8),
        (7, 8),
        (8, 8),
        (8, 7),
        (8, 5),
        (8, 4),
        (8, 3),
        (8, 2),
        (8, 1),
        (8, 0),
    )
    secondary = tuple((8, _SIZE - 1 - index) for index in range(8))
    secondary += tuple((_SIZE - 7 + index, 8) for index in range(7))
    return primary + secondary


def _place(modules: list[list[bool]], reserved: list[list[bool]], bits: list[bool]) -> None:
    index = 0
    col = _SIZE - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(_SIZE - 1, -1, -1) if upward else range(_SIZE)
        for row in rows:
            for current in (col, col - 1):
                if reserved[row][current]:
                    continue
                modules[row][current] = bits[index]
                index += 1
        upward = not upward
        col -= 2
    if index != len(bits):
        raise RuntimeError("qr placement")


def _mask(modules: list[list[bool]], reserved: list[list[bool]]) -> None:
    for row in range(_SIZE):
        for col in range(_SIZE):
            if reserved[row][col]:
                continue
            if (row + col) % 2 == 0:
                modules[row][col] = not modules[row][col]


def _write_format(modules: list[list[bool]], bits: int) -> None:
    positions = _format_positions()
    for shift, (row, col) in enumerate(positions[:15]):
        modules[row][col] = bool((bits >> shift) & 1)
    for shift, (row, col) in enumerate(positions[15:]):
        modules[row][col] = bool((bits >> shift) & 1)
