"""Fixed answer box and corner marks. Coordinates are a function of the page.

One item is one page. order_no is that page's number. The box is the same
rectangle on every page, so a later crop can recover it from the paper record.
"""

from __future__ import annotations

BOX_X = 72
BOX_Y = 220
BOX_W = 451
BOX_H = 220
MARK = 18
_PAGE_W = 595
_PAGE_H = 842


def answer_box(order_no: int) -> tuple[int, int, int, int]:
    """Return x, y, width, height in PDF points. order_no selects the page."""
    if order_no < 1:
        raise ValueError("order_no")
    return (BOX_X, BOX_Y, BOX_W, BOX_H)


def alignment_marks() -> tuple[tuple[int, int, int, int], ...]:
    """Four filled squares, one in each corner. The same on every page."""
    inset = 18
    return (
        (inset, inset, MARK, MARK),
        (_PAGE_W - inset - MARK, inset, MARK, MARK),
        (inset, _PAGE_H - inset - MARK, MARK, MARK),
        (_PAGE_W - inset - MARK, _PAGE_H - inset - MARK, MARK, MARK),
    )


def qr_origin() -> tuple[int, int, int]:
    """Left, bottom, and module size of the code, in PDF points."""
    module = 3
    quiet = 18 + MARK + 8
    return (_PAGE_W - quiet - 29 * module, _PAGE_H - quiet - 29 * module, module)
