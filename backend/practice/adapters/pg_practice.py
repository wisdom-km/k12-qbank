"""PostgreSQL papers, pages, attempts, and confirmations. SQL stays in this file."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from psycopg.errors import UniqueViolation

from backend.kernel.result import Err, StoreFault
from backend.practice.adapters.memory import _issue_inputs_ok
from backend.practice.domain.confirm import (
    Confirmation,
    ConfirmationScope,
    OperationKey,
    PendingAnswer,
    decide_commit,
    scope_of,
)
from backend.practice.domain.paper import Paper

T = TypeVar("T")

_PAPER = """
paper_id, teacher_id, student_id, subject_id, question_version_id, answer_version_id,
asset_ids, layout_template_id, review_version_id, file_id, status, item_order, file_checksum, formula,
qr_printed, printed_external_id, slots_per_page, layout_kind, layout_params, issued_on
"""
_ANSWER = """
fixture_answer_id, paper_id, sub_question_id, review_version_id, student_id, status, answer_text
"""
_CONFIRM = """
confirmation_id, operation_key, paper_id, sub_question_id, teacher_id,
review_version_id, decision, fixture_answer_id
"""


class PgPractice:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    def add_paper(self, paper: Paper) -> None:
        _run(self._pool, lambda conn: _save_paper(conn, paper))

    def replace_paper(self, paper: Paper) -> None:
        def work(conn: Any) -> None:
            if _paper(conn, paper.paper_id) is None:
                raise StoreFault("paper_not_found")
            _save_paper(conn, paper)

        _run(self._pool, work)

    def get_paper(self, paper_id: str) -> Paper | None:
        return _run(self._pool, lambda conn: _paper(conn, paper_id))

    def require_paper(self, paper_id: str) -> Paper:
        found = self.get_paper(paper_id)
        if found is None:
            raise StoreFault("paper_not_found")
        return found

    def paper_count(self) -> int:
        return _count(self._pool, "SELECT count(*) FROM papers")

    def list_papers(self) -> tuple[Paper, ...]:
        return _run(self._pool, lambda conn: tuple(_paper(conn, row[0]) for row in _ids(conn, "papers", "paper_id")))  # type: ignore[misc]

    def find_paper_by_file(self, file_id: str) -> Paper | None:
        statement = f"SELECT {_PAPER} FROM papers WHERE file_id = %s LIMIT 1"
        return _run(self._pool, lambda conn: _one_paper(conn, statement, (file_id,)))

    def find_answer_for_paper(self, paper_id: str) -> PendingAnswer | None:
        statement = f"SELECT {_ANSWER} FROM attempts WHERE paper_id = %s LIMIT 1"
        return _run(self._pool, lambda conn: _one_answer(conn, statement, (paper_id,)))

    def find_answer_for_review(
        self, paper_id: str, sub_question_id: str, review_version_id: str
    ) -> PendingAnswer | None:
        statement = f"""
            SELECT {_ANSWER} FROM attempts
            WHERE paper_id = %s AND sub_question_id = %s AND review_version_id = %s
            LIMIT 1
        """
        params = (paper_id, sub_question_id, review_version_id)
        return _run(self._pool, lambda conn: _one_answer(conn, statement, params))

    def set_review_version(self, paper_id: str, review_version_id: str) -> None:
        def work(conn: Any) -> None:
            updated = conn.execute(
                "UPDATE papers SET review_version_id = %s WHERE paper_id = %s",
                (review_version_id, paper_id),
            )
            if updated.rowcount == 0:
                raise StoreFault("paper_not_found")

        _run(self._pool, work)

    def get_confirmation(self, scope: ConfirmationScope) -> Confirmation | None:
        return _run(self._pool, lambda conn: _confirmation_scope(conn, scope))

    def find_slot(self, paper_id: str, sub_question_id: str, review_version_id: str) -> ConfirmationScope | None:
        statement = f"""
            SELECT {_CONFIRM} FROM confirmations
            WHERE paper_id = %s AND sub_question_id = %s AND review_version_id = %s
        """
        params = (paper_id, sub_question_id, review_version_id)
        found = _run(self._pool, lambda conn: _one_confirmation(conn, statement, params))
        if found is None:
            return None
        return scope_of(found)

    def put_answer(self, answer: PendingAnswer) -> None:
        _run(self._pool, lambda conn: _save_answer(conn, answer))

    def place_issued(self, paper: Paper, answer: PendingAnswer) -> None:
        if not _issue_inputs_ok(paper, answer):
            raise ValueError("incomplete issue")

        def work(conn: Any) -> None:
            _save_paper(conn, paper)
            _save_answer(conn, answer)

        _run(self._pool, work)

    def commit_confirmation(self, record: Confirmation) -> Confirmation | Err:
        try:
            return _run(self._pool, lambda conn: _commit(conn, record))
        except UniqueViolation as exc:
            return _slot_or_raise(exc)

    def insert_confirmation(self, record: Confirmation) -> None:
        try:
            _run(self._pool, lambda conn: _insert_confirmation(conn, record))
        except UniqueViolation as exc:
            raised = _slot_or_raise(exc)
            if isinstance(raised, Err):
                raise StoreFault(raised.code) from exc
            raise

    def confirmation_count(self) -> int:
        return _count(self._pool, "SELECT count(*) FROM confirmations")

    def list_confirmations(self) -> tuple[Confirmation, ...]:
        statement = f"SELECT {_CONFIRM} FROM confirmations ORDER BY confirmation_id"
        return _run(self._pool, lambda conn: tuple(_confirmation(row) for row in conn.execute(statement).fetchall()))


def _run(pool: object, work: Callable[[Any], T]) -> T:
    with pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.transaction():
            return work(conn)


def _count(pool: object, statement: str) -> int:
    row = _run(pool, lambda conn: conn.execute(statement).fetchone())
    return int(row[0])


def _commit(conn: Any, record: Confirmation) -> Confirmation | Err:
    paper = _paper(conn, record.paper_id)
    existing = _confirmation_scope(conn, scope_of(record))
    answer = _answer_by_id(conn, record.fixture_answer_id)
    slot = (record.paper_id, record.sub_question_id, record.review_version_id)
    held = _find_held(conn, slot)
    taken = held is not None and held != scope_of(record)
    placed = decide_commit(paper=paper, existing=existing, answer=answer, slot_taken=taken, record=record)
    if isinstance(placed, Err) or existing is not None:
        return placed
    _insert_confirmation(conn, placed)
    return placed


def _find_held(conn: Any, slot: tuple[str, str, str]) -> ConfirmationScope | None:
    statement = f"""
        SELECT {_CONFIRM} FROM confirmations
        WHERE paper_id = %s AND sub_question_id = %s AND review_version_id = %s
    """
    found = _one_confirmation(conn, statement, slot)
    if found is None:
        return None
    return scope_of(found)


def _slot_or_raise(exc: UniqueViolation) -> Err:
    if (exc.diag.constraint_name or "") == "confirmations_slot_key":
        return Err("slot_conflict", "slot_conflict")
    raise exc


def _save_paper(conn: Any, paper: Paper) -> None:
    conn.execute(
        f"""
        INSERT INTO papers ({_PAPER})
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date)
        ON CONFLICT (paper_id) DO UPDATE SET
            teacher_id = EXCLUDED.teacher_id,
            student_id = EXCLUDED.student_id,
            subject_id = EXCLUDED.subject_id,
            question_version_id = EXCLUDED.question_version_id,
            answer_version_id = EXCLUDED.answer_version_id,
            asset_ids = EXCLUDED.asset_ids,
            layout_template_id = EXCLUDED.layout_template_id,
            review_version_id = EXCLUDED.review_version_id,
            file_id = EXCLUDED.file_id,
            status = EXCLUDED.status,
            item_order = EXCLUDED.item_order,
            file_checksum = EXCLUDED.file_checksum,
            formula = EXCLUDED.formula,
            qr_printed = EXCLUDED.qr_printed,
            printed_external_id = EXCLUDED.printed_external_id,
            slots_per_page = EXCLUDED.slots_per_page,
            layout_kind = EXCLUDED.layout_kind,
            layout_params = EXCLUDED.layout_params
        """,
        _paper_params(paper),
    )
    found = conn.execute("SELECT 1 FROM paper_pages WHERE paper_id = %s LIMIT 1", (paper.paper_id,)).fetchone()
    if found is None:
        _save_page(conn, paper)


def _save_page(conn: Any, paper: Paper) -> None:
    conn.execute(
        """
        INSERT INTO paper_pages (
            paper_id, page_number, page_count, question_version_id, answer_version_id,
            formula, student_id, item_order, asset_ids, layout_template_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (paper_id, page_number) DO UPDATE SET
            page_count = EXCLUDED.page_count,
            question_version_id = EXCLUDED.question_version_id,
            answer_version_id = EXCLUDED.answer_version_id,
            formula = EXCLUDED.formula,
            student_id = EXCLUDED.student_id,
            item_order = EXCLUDED.item_order,
            asset_ids = EXCLUDED.asset_ids,
            layout_template_id = EXCLUDED.layout_template_id
        """,
        (
            paper.paper_id,
            1,
            1,
            paper.question_version_id,
            paper.answer_version_id,
            paper.formula,
            paper.student_id,
            list(paper.item_order),
            list(paper.asset_ids),
            paper.layout_template_id,
        ),
    )


def _save_answer(conn: Any, answer: PendingAnswer) -> None:
    conn.execute(
        f"""
        INSERT INTO attempts ({_ANSWER}) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fixture_answer_id) DO UPDATE SET
            paper_id = EXCLUDED.paper_id,
            sub_question_id = EXCLUDED.sub_question_id,
            review_version_id = EXCLUDED.review_version_id,
            student_id = EXCLUDED.student_id,
            status = EXCLUDED.status,
            answer_text = EXCLUDED.answer_text
        """,
        (
            answer.fixture_answer_id,
            answer.paper_id,
            answer.sub_question_id,
            answer.review_version_id,
            answer.student_id,
            answer.status,
            answer.answer_text,
        ),
    )


def _insert_confirmation(conn: Any, record: Confirmation) -> None:
    conn.execute(
        f"INSERT INTO confirmations ({_CONFIRM}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            record.confirmation_id,
            record.operation_key.value,
            record.paper_id,
            record.sub_question_id,
            record.teacher_id,
            record.review_version_id,
            record.decision,
            record.fixture_answer_id,
        ),
    )


def _paper(conn: Any, paper_id: str) -> Paper | None:
    return _one_paper(conn, f"SELECT {_PAPER} FROM papers WHERE paper_id = %s", (paper_id,))


def _one_paper(conn: Any, statement: str, params: tuple[object, ...]) -> Paper | None:
    row = conn.execute(statement, params).fetchone()
    if row is None:
        return None
    return _paper_row(row)


def _answer_by_id(conn: Any, fixture_answer_id: str) -> PendingAnswer | None:
    statement = f"SELECT {_ANSWER} FROM attempts WHERE fixture_answer_id = %s"
    return _one_answer(conn, statement, (fixture_answer_id,))


def _one_answer(conn: Any, statement: str, params: tuple[object, ...]) -> PendingAnswer | None:
    row = conn.execute(statement, params).fetchone()
    if row is None:
        return None
    return PendingAnswer(
        fixture_answer_id=str(row[0]),
        paper_id=str(row[1]),
        sub_question_id=str(row[2]),
        review_version_id=str(row[3]),
        student_id=str(row[4]),
        status=str(row[5]),
        answer_text=str(row[6]),
    )


def _confirmation_scope(conn: Any, scope: ConfirmationScope) -> Confirmation | None:
    statement = f"""
        SELECT {_CONFIRM} FROM confirmations
        WHERE paper_id = %s AND sub_question_id = %s AND teacher_id = %s AND operation_key = %s
    """
    params = (scope.paper_id, scope.sub_question_id, scope.teacher_id, scope.operation_key.value)
    return _one_confirmation(conn, statement, params)


def _one_confirmation(conn: Any, statement: str, params: tuple[object, ...]) -> Confirmation | None:
    row = conn.execute(statement, params).fetchone()
    if row is None:
        return None
    return _confirmation(row)


def _ids(conn: Any, table: str, column: str) -> list[tuple[object, ...]]:
    if table not in {"papers"} or column not in {"paper_id"}:
        raise StoreFault("store_failed")
    return list(conn.execute(f"SELECT {column} FROM {table} ORDER BY {column}").fetchall())


def _paper_params(paper: Paper) -> tuple[object, ...]:
    return (
        paper.paper_id,
        paper.teacher_id,
        paper.student_id,
        paper.subject_id,
        paper.question_version_id,
        paper.answer_version_id,
        list(paper.asset_ids),
        paper.layout_template_id,
        paper.review_version_id,
        paper.file_id,
        paper.status,
        list(paper.item_order),
        paper.file_checksum,
        paper.formula,
        paper.qr_printed,
        paper.printed_external_id,
        paper.slots_per_page,
        paper.layout_kind,
        paper.layout_params or None,
        paper.issued_on,
    )


def _paper_row(row: tuple[object, ...]) -> Paper:
    return Paper(
        paper_id=str(row[0]),
        teacher_id=str(row[1]),
        student_id=str(row[2]),
        subject_id=str(row[3]),
        question_version_id=str(row[4]),
        answer_version_id=str(row[5]),
        asset_ids=_texts(row[6]),
        layout_template_id=str(row[7]),
        review_version_id=str(row[8]),
        file_id=None if row[9] is None else str(row[9]),
        status=str(row[10]),
        item_order=_texts(row[11]),
        file_checksum=None if row[12] is None else str(row[12]),
        formula=str(row[13]),
        qr_printed=bool(row[14]),
        printed_external_id=str(row[15]),
        slots_per_page=int(row[16]),  # type: ignore[arg-type]
        layout_kind=str(row[17]) if row[17] is not None else "slots",
        layout_params="" if row[18] is None else str(row[18]),
        issued_on="" if row[19] is None else str(row[19]),
    )


def _confirmation(row: tuple[object, ...]) -> Confirmation:
    return Confirmation(
        confirmation_id=str(row[0]),
        operation_key=OperationKey(str(row[1])),
        paper_id=str(row[2]),
        sub_question_id=str(row[3]),
        teacher_id=str(row[4]),
        review_version_id=str(row[5]),
        decision=str(row[6]),
        fixture_answer_id=str(row[7]),
    )


def _texts(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)  # type: ignore[union-attr]
