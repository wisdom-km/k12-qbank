"""Error as data. Use cases return Ok or Err. They do not raise for business refusal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T


@dataclass(frozen=True)
class Err:
    code: str
    message: str


class StoreFault(Exception):
    """A mapped store refusal. Callers turn it into Err. It is not a crash."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


