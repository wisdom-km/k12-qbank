"""One use case, one transaction. Business refusal stays an Err."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from backend.identity.application.conflict import Conflict
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit

T = TypeVar("T")


def execute(opener: Callable[[], Iterator[T]], work: Callable[[T], Ok[object] | Err], logger: object, request_id: str) -> Ok[object] | Err:
    import time

    started_at = time.perf_counter()
    try:
        with opener() as db:
            return work(db)
    except Conflict as exc:
        return Err(exc.code, exc.code)
    except Exception:
        emit(
            logger,  # type: ignore[arg-type]
            level="ERROR",
            event="use_case_failed",
            request_id=request_id,
            module="identity",
            outcome="store_failed",
            started=started_at,
        )
        return Err("store_failed", "the store failed")


@contextmanager
def memory_scope(stores: T) -> Iterator[T]:
    yield stores
