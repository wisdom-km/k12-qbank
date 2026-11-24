"""PostgreSQL runs. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from psycopg.errors import UniqueViolation

from backend.ai.domain.records import Run, Suggestion
from backend.kernel.result import StoreFault

T = TypeVar("T")


class PgRuns:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def insert(self, run: Run) -> None:
        def work(conn: Any) -> None:
            try:
                conn.execute(
                    """
                    INSERT INTO ai_run (
                        run_id, intake_id, provider, model, prompt_version, status,
                        error_code, started_at, finished_at, input_tokens, output_tokens,
                        external_match, page_match
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    _run_params(run),
                )
            except UniqueViolation as exc:
                if (exc.diag.constraint_name or "") == "ai_run_active":
                    raise StoreFault("ai_run_in_progress") from None
                raise

        _run(self._pool, work)

    def get(self, run_id: str) -> Run | None:
        def work(conn: Any) -> Run | None:
            row = conn.execute(
                """
                SELECT run_id, intake_id, provider, model, prompt_version, status,
                       error_code, started_at, finished_at, input_tokens, output_tokens,
                       external_match, page_match
                FROM ai_run WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            suggestions = conn.execute(
                """
                SELECT run_id, paper_id, order_no, transcription, unreadable, confidence,
                       verdict, reason, judged_by
                FROM ai_suggestion
                WHERE run_id = %s
                ORDER BY order_no
                """,
                (run_id,),
            ).fetchall()
            return _run_row(row, tuple(_suggestion(item) for item in suggestions))

        return _run(self._pool, work)

    def count_started_on(self, day: str) -> int:
        start = datetime.fromisoformat(day + "T00:00:00+00:00")
        end = start + timedelta(days=1)
        row = _run(
            self._pool,
            lambda conn: conn.execute(
                "SELECT count(*) FROM ai_run WHERE started_at >= %s AND started_at < %s",
                (start, end),
            ).fetchone(),
        )
        return int(row[0]) if row is not None else 0

    def mark_running(self, run_id: str) -> bool:
        def work(conn: Any) -> bool:
            updated = conn.execute(
                """
                UPDATE ai_run SET status = 'running'
                WHERE run_id = %s AND status = 'queued'
                """,
                (run_id,),
            )
            return int(updated.rowcount) == 1

        return _run(self._pool, work)

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        error_code: str,
        input_tokens: int | None,
        output_tokens: int | None,
        external_match: str,
        page_match: str,
        suggestions: tuple[Suggestion, ...],
    ) -> None:
        def work(conn: Any) -> None:
            conn.execute(
                """
                UPDATE ai_run
                SET status = %s, error_code = %s, finished_at = %s,
                    input_tokens = %s, output_tokens = %s,
                    external_match = %s, page_match = %s
                WHERE run_id = %s
                """,
                (
                    status,
                    _empty(error_code),
                    datetime.now(timezone.utc),
                    input_tokens,
                    output_tokens,
                    _empty(external_match),
                    _empty(page_match),
                    run_id,
                ),
            )
            for item in suggestions:
                conn.execute(
                    """
                    INSERT INTO ai_suggestion (
                        run_id, paper_id, order_no, transcription, unreadable, confidence,
                        verdict, reason, judged_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item.run_id,
                        item.paper_id,
                        item.order_no,
                        item.transcription,
                        item.unreadable,
                        item.confidence,
                        item.verdict,
                        item.reason,
                        item.judged_by,
                    ),
                )

        _run(self._pool, work)

    def interrupt_open(self) -> int:
        def work(conn: Any) -> int:
            updated = conn.execute(
                """
                UPDATE ai_run
                SET status = 'failed', error_code = 'interrupted', finished_at = %s
                WHERE status IN ('queued', 'running')
                """,
                (datetime.now(timezone.utc),),
            )
            return int(updated.rowcount)

        return _run(self._pool, work)


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _run_params(run: Run) -> tuple[object, ...]:
    return (
        run.run_id,
        run.intake_id,
        run.provider,
        run.model,
        run.prompt_version,
        run.status,
        _empty(run.error_code),
        _stamp(run.started_at),
        _stamp(run.finished_at) if run.finished_at else None,
        run.input_tokens,
        run.output_tokens,
        _empty(run.external_match),
        _empty(run.page_match),
    )


def _run_row(row: tuple[object, ...], suggestions: tuple[Suggestion, ...]) -> Run:
    return Run(
        run_id=str(row[0]),
        intake_id=str(row[1]),
        provider=str(row[2]),
        model=str(row[3]),
        prompt_version=str(row[4]),
        status=str(row[5]),
        error_code="" if row[6] is None else str(row[6]),
        started_at=_text_time(row[7]),
        finished_at=_text_time(row[8]),
        input_tokens=None if row[9] is None else int(row[9]),  # type: ignore[arg-type]
        output_tokens=None if row[10] is None else int(row[10]),  # type: ignore[arg-type]
        external_match="" if row[11] is None else str(row[11]),
        page_match="" if row[12] is None else str(row[12]),
        suggestions=suggestions,
    )


def _suggestion(row: tuple[object, ...]) -> Suggestion:
    return Suggestion(
        run_id=str(row[0]),
        paper_id=str(row[1]),
        order_no=int(row[2]),  # type: ignore[arg-type]
        transcription=str(row[3]),
        unreadable=bool(row[4]),
        confidence=float(row[5]),  # type: ignore[arg-type]
        verdict=str(row[6]),
        reason=str(row[7]),
        judged_by=str(row[8]),
    )


def _empty(value: str) -> str | None:
    return value if value else None


def _stamp(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _text_time(value: object) -> str:
    if value is None:
        return ""
    iso = getattr(value, "isoformat", None)
    text = iso() if iso is not None else str(value)
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text
