"""Import one whole book. Namespace keys once, then the stores see only those keys.

Each store opens its own connection. A later import of the same book is kept
once the approval snapshot exists.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, replace
from typing import Protocol

from backend.catalog.application.stage_review import _plain, _version_id, stage_review, subject_accepted
from backend.catalog.domain.answer import AnswerDraft, parse_answer_draft
from backend.catalog.domain.book_key import namespace_reason, namespaced_key
from backend.catalog.domain.parse import parse_question_draft
from backend.catalog.domain.snapshot import ApprovalSnapshot
from backend.catalog.domain.validate import DraftFile, QuestionDraft
from backend.kernel.logger import Logger
from backend.kernel.result import Err
from backend.kernel.use_log import emit

_MAX_PAGES = 600
_PAGE_KEYS = {"pdf_page", "role", "questions", "answers"}
_PAIR_KEYS = {"answer_page", "question_page", "keys"}


class _Questions(Protocol):
    def save(self, draft: DraftFile) -> None: ...

    def read(self, key: str) -> QuestionDraft | None: ...


class _Answers(Protocol):
    def put(self, answer: AnswerDraft) -> str | None: ...


class _Approvals(Protocol):
    def read_snapshot(self, question_version_id: str) -> ApprovalSnapshot | None: ...

    def insert_if_absent(self, snapshot: ApprovalSnapshot) -> bool: ...


@dataclass(frozen=True)
class PageResult:
    pdf_page: int | None
    role: str
    outcome: str
    reason: str


@dataclass(frozen=True)
class QuestionResult:
    original_key: str
    key: str
    question_version_id: str
    outcome: str
    reason: str


@dataclass(frozen=True)
class BookImportReport:
    book_id: str
    dry_run: bool
    written: bool
    pages: tuple[PageResult, ...]
    questions: tuple[QuestionResult, ...]
    staged: int
    kept: int
    skipped: int
    conflict: int
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "book_id": self.book_id,
            "dry_run": self.dry_run,
            "written": self.written,
            "reason": self.reason,
            "pages": [
                {
                    "pdf_page": page.pdf_page,
                    "role": page.role,
                    "outcome": page.outcome,
                    "reason": page.reason,
                }
                for page in self.pages
            ],
            "questions": [
                {
                    "original_key": row.original_key,
                    "key": row.key,
                    "question_version_id": row.question_version_id,
                    "outcome": row.outcome,
                    "reason": row.reason,
                }
                for row in self.questions
            ],
            "staged": self.staged,
            "kept": self.kept,
            "skipped": self.skipped,
            "conflict": self.conflict,
        }


@dataclass
class _Page:
    pdf_page: int | None
    role: str
    reason: str
    file_page: int | None
    questions: list[tuple[str, QuestionDraft]]
    answers: list[AnswerDraft]


@dataclass
class _Planned:
    page: int
    original_key: str
    question: QuestionDraft
    answer: AnswerDraft | None
    outcome: str
    reason: str
    version_id: str
    save_question: bool


@dataclass(frozen=True)
class _Pair:
    answer_page: int
    question_page: int
    keys: tuple[str, ...] | None


def import_book(
    book_id: str,
    subject_id: str,
    pages: object,
    pairing: object,
    questions: _Questions,
    answers: _Answers,
    approvals: _Approvals,
    logger: Logger,
    request_id: str,
    *,
    dry_run: bool = False,
    unknown_fields: bool = False,
    actor_user_id: str = "",
) -> BookImportReport:
    """Validate the whole book, then write staged rows. A page error writes nothing."""
    started = time.perf_counter()
    report = _build(
        book_id,
        subject_id,
        pages,
        pairing,
        questions,
        answers,
        approvals,
        dry_run=dry_run,
        unknown_fields=unknown_fields,
    )
    _audit(logger, request_id, actor_user_id, book_id, pages, report, started)
    return report


def _build(
    book_id: str,
    subject_id: str,
    pages: object,
    pairing: object,
    questions: _Questions,
    answers: _Answers,
    approvals: _Approvals,
    *,
    dry_run: bool,
    unknown_fields: bool,
) -> BookImportReport:
    if unknown_fields:
        return _finish(book_id, dry_run, (), (), "unknown_field", False)
    if namespace_reason(book_id, 1, "1") == "invalid_book_id":
        return _finish(book_id if isinstance(book_id, str) else "", dry_run, (), (), "invalid_book_id", False)
    if not isinstance(subject_id, str) or not subject_accepted(subject_id):
        return _finish(book_id, dry_run, (), (), "invalid_subject", False)
    if not isinstance(pages, list) or not isinstance(pairing, list):
        return _finish(book_id, dry_run, (), (), "unknown_field", False)
    if len(pages) > _MAX_PAGES:
        return _finish(book_id, dry_run, (), (), "too_many_pages", False)
    loaded, envelope = _load_pages(pages)
    if envelope:
        return _finish(book_id, dry_run, _page_rows(loaded), (), envelope, False)
    pairs, pair_reason = _load_pairs(pairing)
    if pair_reason:
        return _finish(book_id, dry_run, _page_rows(loaded), (), pair_reason, False)
    _mark_duplicates(loaded)
    planned, pair_pages = _assign(book_id, loaded, pairs)
    _classify(planned, questions, approvals)
    page_rows = _page_rows(loaded)
    page_rows.extend(pair_pages)
    blocked = any(page.reason for page in page_rows) or any(item.outcome == "conflict" for item in planned)
    question_rows = _question_rows(planned)
    if blocked or dry_run:
        return _finish(book_id, dry_run, tuple(page_rows), question_rows, "", False)
    _persist(planned, questions, answers, approvals, subject_id)
    return _finish(book_id, dry_run, tuple(page_rows), question_rows, "", True)


def _finish(
    book_id: str,
    dry_run: bool,
    pages: tuple[PageResult, ...] | list[PageResult],
    questions: tuple[QuestionResult, ...],
    reason: str,
    written: bool,
) -> BookImportReport:
    rows = tuple(pages)
    return BookImportReport(
        book_id=book_id,
        dry_run=dry_run,
        written=written,
        pages=rows,
        questions=questions,
        staged=sum(row.outcome == "staged" for row in questions),
        kept=sum(row.outcome == "kept" for row in questions),
        skipped=sum(row.outcome == "skipped" for row in questions),
        conflict=sum(row.outcome == "conflict" for row in questions),
        reason=reason,
    )


def _load_pages(pages: list[object]) -> tuple[list[_Page], str]:
    loaded: list[_Page] = []
    for raw in pages:
        if not isinstance(raw, dict) or set(raw) - _PAGE_KEYS:
            return loaded, "unknown_field"
        role = raw.get("role")
        number = _whole_page(raw.get("pdf_page"))
        if role not in {"questions", "answers"}:
            loaded.append(_Page(number, "" if role is None else str(role), "unknown_field", None, [], []))
            continue
        if number is None:
            loaded.append(_Page(None, role, "page_missing", None, [], []))
            continue
        if role == "answers" and raw.get("questions") not in (None,):
            if "questions" in raw and raw.get("questions") is not None:
                loaded.append(_Page(number, role, "unknown_field", None, [], []))
                continue
        draft = raw.get("questions")
        answer_rows = raw.get("answers", [])
        if role == "questions" and not isinstance(draft, dict):
            loaded.append(_Page(number, role, "page_missing", None, [], []))
            continue
        if not isinstance(answer_rows, list):
            return loaded, "unknown_field"
        reason, file_page = _declared_source(draft if isinstance(draft, dict) else None, answer_rows, number, role)
        if reason:
            loaded.append(_Page(number, role, reason, file_page, [], []))
            continue
        questions, answers, parse_reason = _parse_page(draft if isinstance(draft, dict) else None, answer_rows, role)
        if parse_reason:
            loaded.append(_Page(number, role, parse_reason, file_page, [], []))
            continue
        dup = _duplicate_key(questions, answers)
        loaded.append(_Page(number, role, dup, file_page, questions, answers))
    return loaded, ""


def _declared_source(
    draft: dict[str, object] | None,
    answer_rows: list[object],
    number: int,
    role: str,
) -> tuple[str, int | None]:
    if role == "questions":
        assert draft is not None
        reason, page = _source_page(draft)
        if reason:
            return reason, page
        if page != number:
            return "page_mismatch", page
    for raw in answer_rows:
        if not isinstance(raw, dict):
            return "not_draft", None
        reason, page = _source_page(raw)
        if reason:
            return reason, page
        if page != number:
            return "page_mismatch", page
    return "", number


def _source_page(payload: dict[str, object]) -> tuple[str, int | None]:
    source = payload.get("source")
    if not isinstance(source, dict) or "pdf_page" not in source:
        return "page_missing", None
    page = source.get("pdf_page")
    if page is None:
        return "page_missing", None
    if isinstance(page, bool) or not isinstance(page, int):
        return "page_mismatch", None
    return "", page


def _parse_page(
    draft: dict[str, object] | None,
    answer_rows: list[object],
    role: str,
) -> tuple[list[tuple[str, QuestionDraft]], list[AnswerDraft], str]:
    questions: list[tuple[str, QuestionDraft]] = []
    if role == "questions":
        assert draft is not None
        parsed = parse_question_draft(draft)
        if isinstance(parsed, Err):
            return [], [], parsed.code
        questions = [(item.key, item) for item in parsed.value.questions]
    answers: list[AnswerDraft] = []
    for raw in answer_rows:
        parsed_answer = parse_answer_draft(raw)
        if isinstance(parsed_answer, Err):
            return [], [], parsed_answer.code
        answers.append(parsed_answer.value)
    return questions, answers, ""


def _duplicate_key(questions: list[tuple[str, QuestionDraft]], answers: list[AnswerDraft]) -> str:
    seen_questions: set[str] = set()
    for key, _question in questions:
        if key in seen_questions:
            return "duplicate_question_key"
        seen_questions.add(key)
    seen_answers: set[str] = set()
    for answer in answers:
        if answer.key in seen_answers:
            return "duplicate_answer_key"
        seen_answers.add(answer.key)
    return ""


def _load_pairs(pairing: list[object]) -> tuple[list[_Pair], str]:
    pairs: list[_Pair] = []
    for raw in pairing:
        if not isinstance(raw, dict) or set(raw) - _PAIR_KEYS:
            return [], "unknown_field"
        if "answer_page" not in raw or "question_page" not in raw:
            return [], "unknown_field"
        answer_page = _whole_page(raw.get("answer_page"))
        question_page = _whole_page(raw.get("question_page"))
        if answer_page is None or question_page is None:
            return [], "page_missing"
        keys: tuple[str, ...] | None = None
        if "keys" in raw and raw.get("keys") is not None:
            listed = raw.get("keys")
            if not isinstance(listed, list) or any(not isinstance(item, str) for item in listed):
                return [], "unknown_field"
            keys = tuple(listed)
        pairs.append(_Pair(answer_page, question_page, keys))
    return pairs, ""


def _mark_duplicates(pages: list[_Page]) -> None:
    numbers = [page.pdf_page for page in pages if page.pdf_page is not None]
    repeated = {number for number, count in Counter(numbers).items() if count > 1}
    for page in pages:
        if page.reason:
            continue
        if page.pdf_page in repeated:
            page.reason = "duplicate_page"


def _assign(book_id: str, pages: list[_Page], pairs: list[_Pair]) -> tuple[list[_Planned], list[PageResult]]:
    by_number = {page.pdf_page: page for page in pages if page.pdf_page is not None and not page.reason}
    questions_on: dict[int, set[str]] = {
        number: {key for key, _question in page.questions}
        for number, page in by_number.items()
        if page.role == "questions"
    }
    extra: list[PageResult] = []
    assigned: dict[tuple[int, str], int] = {}
    reasons: dict[tuple[int, str], str] = {}
    for page in pages:
        if page.reason or page.role != "questions" or page.pdf_page is None:
            continue
        for answer in page.answers:
            token = (page.pdf_page, answer.key)
            if answer.question_key not in questions_on.get(page.pdf_page, set()):
                reasons[token] = "no_question"
            else:
                assigned[token] = page.pdf_page
    for page in pages:
        if page.reason or page.role != "answers" or page.pdf_page is None:
            continue
        for answer in page.answers:
            token = (page.pdf_page, answer.key)
            targets = [
                pair.question_page
                for pair in pairs
                if pair.answer_page == page.pdf_page
                and (pair.keys is None or answer.question_key in pair.keys)
            ]
            unique = set(targets)
            if len(unique) > 1:
                reasons[token] = "pairing_overlap"
            elif len(unique) == 0:
                reasons[token] = "unpaired_answer"
            else:
                target = targets[0]
                if answer.question_key not in questions_on.get(target, set()):
                    reasons[token] = "no_question"
                else:
                    assigned[token] = target
    for pair in pairs:
        if pair.keys is None:
            continue
        host = by_number.get(pair.answer_page)
        known = set()
        if host is not None and host.role == "answers" and not host.reason:
            known = {answer.question_key for answer in host.answers}
        for key in pair.keys:
            if key not in known:
                extra.append(PageResult(pair.answer_page, "answers", "rejected", "no_question"))
    for page in pages:
        if page.reason or page.pdf_page is None:
            continue
        for _key, answer in ((answer.key, answer) for answer in page.answers):
            token = (page.pdf_page, answer.key)
            if token in reasons and not page.reason:
                page.reason = reasons[token]
    planned: list[_Planned] = []
    for page in pages:
        if page.role != "questions" or page.pdf_page is None:
            continue
        adopted = _adopted(pages, assigned, page.pdf_page)
        for original, question in page.questions:
            stored_reason = namespace_reason(book_id, page.pdf_page, original)
            if stored_reason:
                page.reason = page.reason or stored_reason
                planned.append(_Planned(page.pdf_page, original, question, None, "", stored_reason, "", False))
                continue
            answer = adopted.get(original)
            if answer is not None:
                answer_reason = namespace_reason(book_id, page.pdf_page, answer.key)
                if answer_reason:
                    page.reason = page.reason or answer_reason
                    planned.append(_Planned(page.pdf_page, original, question, None, "", answer_reason, "", False))
                    continue
            key = namespaced_key(book_id, page.pdf_page, original)
            renamed = replace(question, key=key)
            renamed_answer = None if answer is None else _rename_answer(book_id, page.pdf_page, answer)
            planned.append(_Planned(page.pdf_page, original, renamed, renamed_answer, "", "", "", False))
    return planned, extra


def _adopted(pages: list[_Page], assigned: dict[tuple[int, str], int], question_page: int) -> dict[str, AnswerDraft]:
    found: dict[str, AnswerDraft] = {}
    for page in pages:
        if page.pdf_page is None:
            continue
        for answer in page.answers:
            if assigned.get((page.pdf_page, answer.key)) != question_page:
                continue
            if answer.applicable:
                found[answer.question_key] = answer
    return found


def _rename_answer(book_id: str, question_page: int, answer: AnswerDraft) -> AnswerDraft:
    return replace(
        answer,
        question_key=namespaced_key(book_id, question_page, answer.question_key),
        key=namespaced_key(book_id, question_page, answer.key),
    )


def _classify(planned: list[_Planned], questions: _Questions, approvals: _Approvals) -> None:
    for item in planned:
        if item.reason:
            continue
        version = _version_id("qv-", item.question.key) or ""
        item.version_id = version
        snapshot = approvals.read_snapshot(version) if version else None
        stored = questions.read(item.question.key)
        if snapshot is not None:
            if item.answer is not None and _same_snapshot(item.question, item.answer, snapshot):
                item.outcome = "kept"
            else:
                item.outcome = "conflict"
                item.reason = "conflict"
            continue
        if stored is not None and not _same_question(item.question, stored):
            item.outcome = "conflict"
            item.reason = "conflict"
            continue
        item.save_question = stored is None
        item.outcome = "skipped" if item.answer is None else "staged"


def _same_question(question: QuestionDraft, stored: QuestionDraft) -> bool:
    return (
        _plain(question.stem) == _plain(stored.stem)
        and _option_text(question) == _option_text(stored)
        and question.type == stored.type
    )


def _same_snapshot(question: QuestionDraft, answer: AnswerDraft, snapshot: ApprovalSnapshot) -> bool:
    return (
        _plain(question.stem) == snapshot.stem
        and _option_text(question) == snapshot.options
        and _plain(answer.content) == snapshot.answer_text
        and question.type == snapshot.type
    )


def _option_text(question: QuestionDraft) -> tuple[str, ...]:
    return tuple(f"{option.key}. {_plain(option.content)}".strip() for option in question.options)


def _persist(
    planned: list[_Planned],
    questions: _Questions,
    answers: _Answers,
    approvals: _Approvals,
    subject_id: str,
) -> None:
    grouped: dict[int, list[QuestionDraft]] = {}
    for item in planned:
        if item.save_question:
            grouped.setdefault(item.page, []).append(item.question)
    for page, rows in grouped.items():
        questions.save(DraftFile(pdf_page=page, ok=True, reason="", preface="", questions=tuple(rows)))
    staged = [item for item in planned if item.outcome == "staged" and item.answer is not None]
    for item in staged:
        assert item.answer is not None
        answers.put(item.answer)
    if not staged:
        return
    stage_review(
        DraftFile(
            pdf_page=staged[0].page,
            ok=True,
            reason="",
            preface="",
            questions=tuple(item.question for item in staged),
        ),
        tuple(item.answer for item in staged if item.answer is not None),
        approvals,
        subject_id,
    )


def _page_rows(pages: list[_Page]) -> list[PageResult]:
    return [
        PageResult(
            page.pdf_page,
            page.role,
            "rejected" if page.reason else "ok",
            page.reason,
        )
        for page in pages
    ]


def _question_rows(planned: list[_Planned]) -> tuple[QuestionResult, ...]:
    return tuple(
        QuestionResult(
            item.original_key,
            "" if item.reason in {"key_too_long", "page_missing", "invalid_book_id"} else item.question.key,
            item.version_id,
            item.outcome,
            item.reason,
        )
        for item in planned
    )


def _whole_page(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _audit(
    logger: Logger,
    request_id: str,
    actor_user_id: str,
    book_id: str,
    pages: object,
    report: BookImportReport,
    started: float,
) -> None:
    page_count = len(pages) if isinstance(pages, list) else 0
    target = book_id if isinstance(book_id, str) and namespace_reason(book_id, 1, "1") == "" else ""
    emit(
        logger,
        level="INFO",
        event="import_book",
        request_id=request_id,
        module="catalog.import_book",
        outcome=(
            f"pages={page_count};staged={report.staged};kept={report.kept};"
            f"skipped={report.skipped};conflict={report.conflict}"
        ),
        started=started,
        actor_user_id=actor_user_id,
        target_kind="book",
        target_id=target,
        audit=True,
    )


