"""In-memory runs. One active row per intake."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone

from backend.ai.domain.records import Run, Suggestion
from backend.kernel.result import StoreFault

_OPEN = frozenset({"queued", "running"})


class MemoryRuns:
    def __init__(self) -> None:
        self._rows: dict[str, Run] = {}
        self._lock = threading.Lock()

    def insert(self, run: Run) -> None:
        with self._lock:
            if any(row.intake_id == run.intake_id and row.status in _OPEN for row in self._rows.values()):
                raise StoreFault("ai_run_in_progress")
            self._rows[run.run_id] = run

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._rows.get(run_id)

    def count_started_on(self, day: str) -> int:
        with self._lock:
            return sum(1 for row in self._rows.values() if row.started_at.startswith(day))

    def mark_running(self, run_id: str) -> bool:
        with self._lock:
            current = self._rows.get(run_id)
            if current is None or current.status != "queued":
                return False
            self._rows[run_id] = replace(current, status="running")
            return True

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
        with self._lock:
            current = self._rows.get(run_id)
            if current is None:
                raise StoreFault("not_found")
            self._rows[run_id] = replace(
                current,
                status=status,
                error_code=error_code,
                finished_at=_now(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                external_match=external_match,
                page_match=page_match,
                suggestions=suggestions,
            )

    def interrupt_open(self) -> int:
        with self._lock:
            count = 0
            for run_id, current in list(self._rows.items()):
                if current.status not in _OPEN:
                    continue
                self._rows[run_id] = replace(
                    current,
                    status="failed",
                    error_code="interrupted",
                    finished_at=_now(),
                )
                count += 1
            return count

    def dump_text(self) -> str:
        """Test helper. Joins stored fields. It does not read a model response."""
        with self._lock:
            parts: list[str] = []
            for row in self._rows.values():
                parts.append(
                    " ".join(
                        (
                            row.run_id,
                            row.intake_id,
                            row.provider,
                            row.model,
                            row.prompt_version,
                            row.status,
                            row.error_code,
                            row.external_match,
                            row.page_match,
                        )
                    )
                )
                for item in row.suggestions:
                    parts.append(
                        " ".join(
                            (
                                str(item.order_no),
                                item.transcription,
                                item.verdict,
                                item.reason,
                                item.judged_by,
                                item.paper_id,
                            )
                        )
                    )
            return "\n".join(parts)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
