"""Book and page namespace for catalog keys.

The same book, page, and original key always produce the same stored key.
A different triple never shares that key. Nothing here reads a database.
"""

from __future__ import annotations

import re

BOOK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
_STORED = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def namespaced_key(book_id: str, pdf_page: int, original_key: str) -> str:
    """Join a book, a question page, and the review tool's key.

    pdf_page is the question page the row belongs to. An answer keeps its own
    source page on the draft. This function does not shorten a long key.
    """
    return f"{book_id}.p{pdf_page:04d}:{original_key}"


def namespace_reason(book_id: str, pdf_page: int, original_key: str) -> str:
    """Return an empty string, invalid_book_id, page_missing, or key_too_long."""
    if not isinstance(book_id, str) or BOOK_ID.fullmatch(book_id) is None:
        return "invalid_book_id"
    if isinstance(pdf_page, bool) or not isinstance(pdf_page, int) or pdf_page < 1:
        return "page_missing"
    if not isinstance(original_key, str):
        return "key_too_long"
    stored = namespaced_key(book_id, pdf_page, original_key)
    if _STORED.fullmatch(stored) is None:
        return "key_too_long"
    return ""
