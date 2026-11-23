"""QR payload and format bits. No scanner and no third-party package."""

from __future__ import annotations

import unittest

from backend.practice.domain.page_layout import answer_box
from backend.practice.domain.qr_code import encode_qr, format_bits, qr_payload

_GENERATOR = 0b10100110111
_MASK = 0b101010000010010


def _bch(mask: int) -> int:
    data = mask & 0b111
    remainder = data << 10
    for shift in range(4, -1, -1):
        if remainder & (1 << (shift + 10)):
            remainder ^= _GENERATOR << shift
    return ((data << 10) | (remainder & 0x3FF)) ^ _MASK


class QrCodeTest(unittest.TestCase):
    def test_payload_is_paper_and_page_only(self) -> None:
        text = qr_payload("abc123", 2)
        self.assertEqual(text, "abc123#2")
        self.assertNotIn("synth-", text)
        self.assertNotIn("student", text)
        with self.assertRaises(ValueError):
            qr_payload("abc", 0)
        with self.assertRaises(ValueError):
            qr_payload("x" * 43, 1)

    def test_format_bits_match_an_independent_bch(self) -> None:
        self.assertEqual(format_bits(0), _bch(0))
        matrix = encode_qr("paper-1#1")
        self.assertEqual(len(matrix), 29)
        self.assertTrue(all(len(row) == 29 for row in matrix))
        self.assertEqual(_read_format(matrix), _bch(0))
        self.assertEqual(_read_format_copy(matrix), _bch(0))

    def test_finders_and_stable_encoding(self) -> None:
        one = encode_qr("paper-1#1")
        again = encode_qr("paper-1#1")
        other = encode_qr("paper-2#1")
        self.assertEqual(one, again)
        self.assertNotEqual(one, other)
        for row, col in ((0, 0), (0, 22), (22, 0)):
            self.assertTrue(one[row][col])
            self.assertTrue(one[row + 6][col + 6])
            self.assertFalse(one[row + 1][col + 1])
        self.assertTrue(one[21][8])
        self.assertEqual(answer_box(1), answer_box(4))
        self.assertEqual(answer_box(1), (72, 220, 451, 220))


def _read_format(matrix: tuple[tuple[bool, ...], ...]) -> int:
    spots = (
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
    return _gather(matrix, spots)


def _read_format_copy(matrix: tuple[tuple[bool, ...], ...]) -> int:
    spots = tuple((8, 28 - index) for index in range(8))
    spots += tuple((22 + index, 8) for index in range(7))
    return _gather(matrix, spots)


def _gather(matrix: tuple[tuple[bool, ...], ...], spots: tuple[tuple[int, int], ...]) -> int:
    value = 0
    for shift, (row, col) in enumerate(spots):
        value |= int(matrix[row][col]) << shift
    return value


if __name__ == "__main__":
    unittest.main()
