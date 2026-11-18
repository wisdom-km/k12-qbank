"""A uniqueness race. The transaction must roll back."""

from __future__ import annotations


class Conflict(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
