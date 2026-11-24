"""Draw one frozen page and store its bytes. A failure leaves the paper waiting."""

from __future__ import annotations

import hashlib
import time

from backend.catalog.api import ApprovalPort
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok
from backend.kernel.use_log import emit, read_store
from backend.practice.application.ports import Authorizer, FileStore, PageRenderer, PracticeItems, PracticeStore
from backend.practice.application.resolve_items import _resolve_items
from backend.practice.domain.item import PracticeItem
from backend.practice.domain.page_face import PaperPage, SlotFace, formula_from_stem
from backend.practice.domain.page_layout import slot_answer_box
from backend.practice.domain.paper import Paper, mark_issued, mark_printable, recall_file


def render_paper(
    paper_id: str,
    approvals: ApprovalPort,
    auth: Authorizer,
    store: PracticeStore,
    files: FileStore,
    renderer: PageRenderer,
    logger: Logger,
    request_id: str,
    *,
    actor_teacher_id: str,
    items: PracticeItems | None = None,
) -> Ok[Paper] | Err:
    started = time.perf_counter()
    loaded = _load_allowed(paper_id, auth, store, logger, request_id, started, actor_teacher_id)
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    if paper.status != "待渲染":
        return _refuse(logger, request_id, started, "not_rendering", "only a paper waiting for render can become printable")
    # The stem and formula were copied at issue. A later bank edit must not change this page.
    resolved = _resolve_items(paper.paper_id, store, items)
    faces = page_faces(paper, resolved)
    if len(faces) == 1:
        drawn = renderer.render(faces[0])
    else:
        draw_document = getattr(renderer, "render_document", None)
        if draw_document is None:
            return _refuse(logger, request_id, started, "not_rendered", "this renderer cannot draw multiple pages")
        drawn = draw_document(faces)
    if isinstance(drawn, Err):
        emit(
            logger,
            level="WARN",
            event="use_case_refused",
            request_id=request_id,
            module="practice.render",
            outcome=drawn.code,
            started=started,
        )
        return drawn
    stored = read_store(
        lambda: files.add(drawn),
        logger,
        request_id,
        "practice.render",
        started,
    )
    if isinstance(stored, Err):
        return stored
    file_id, checksum = stored.value
    printable = mark_printable(paper, file_id=file_id, checksum=checksum)
    if isinstance(printable, Err):
        return _refuse(logger, request_id, started, printable.code, printable.message)
    saved = read_store(
        lambda: store.replace_paper(printable),
        logger,
        request_id,
        "practice.render",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="page_stored",
        request_id=request_id,
        module="practice.render",
        outcome=file_id,
        started=started,
    )
    return Ok(printable)


def hand_out_paper(
    paper_id: str,
    approvals: ApprovalPort,
    auth: Authorizer,
    store: PracticeStore,
    logger: Logger,
    request_id: str,
    *,
    actor_teacher_id: str,
    items: PracticeItems | None = None,
) -> Ok[Paper] | Err:
    """Hand-out reads retirement again. A retired publication does not change the file id."""
    started = time.perf_counter()
    loaded = _load_allowed(paper_id, auth, store, logger, request_id, started, actor_teacher_id)
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    resolved = _resolve_items(paper.paper_id, store, items)
    version_id = resolved[0].question_version_id
    snapshot = read_store(
        lambda: approvals.read_snapshot(version_id),
        logger,
        request_id,
        "practice.handout",
        started,
    )
    if isinstance(snapshot, Err):
        return snapshot
    if snapshot.value is None:
        return _refuse(logger, request_id, started, "not_found", "the question version does not exist")
    issued = mark_issued(paper, publication_retired=snapshot.value.retired)
    if isinstance(issued, Err):
        return _refuse(logger, request_id, started, issued.code, issued.message)
    saved = read_store(
        lambda: store.replace_paper(issued),
        logger,
        request_id,
        "practice.handout",
        started,
    )
    if isinstance(saved, Err):
        return saved
    emit(
        logger,
        level="INFO",
        event="adapter_completed",
        request_id=request_id,
        module="practice.handout",
        outcome=issued.paper_id,
        started=started,
    )
    return Ok(issued)


def read_file(
    file_id: str,
    auth: Authorizer,
    store: PracticeStore,
    files: FileStore,
    logger: Logger,
    request_id: str,
    *,
    actor_teacher_id: str,
) -> Ok[bytes] | Err:
    """Return the bytes stored for this file id. A changed checksum keeps the old id."""
    started = time.perf_counter()
    loaded = read_store(
        lambda: store.find_paper_by_file(file_id),
        logger,
        request_id,
        "practice.file",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    if paper is None:
        return _refuse(logger, request_id, started, "not_rendered", "this paper has no stored file")
    if paper.teacher_id != actor_teacher_id or not auth.allow(
        actor_teacher_id, paper.student_id, paper.subject_id
    ):
        return _refuse(logger, request_id, started, "unauthorized", "this teacher cannot read that file")
    data = read_store(
        lambda: files.read(file_id),
        logger,
        request_id,
        "practice.file",
        started,
    )
    if isinstance(data, Err):
        return data
    if data.value is None or paper.file_checksum is None:
        return _refuse(logger, request_id, started, "not_rendered", "this paper has no stored file")
    digest = hashlib.sha256(data.value).hexdigest()
    blocked = recall_file(paper, file_id=file_id, checksum=digest)
    if blocked is not None:
        return _refuse(logger, request_id, started, blocked.code, blocked.message)
    return Ok(data.value)


def page_faces(paper: Paper, items: tuple[PracticeItem, ...]) -> tuple[PaperPage, ...]:
    """slots_per_page 1 keeps one legacy page per item. 4 groups by page_no."""
    if paper.slots_per_page <= 1:
        count = len(items)
        return tuple(_face(paper, item, count) for item in items)
    grouped: dict[int, list[PracticeItem]] = {}
    for item in items:
        grouped.setdefault(max(item.page_no, 1), []).append(item)
    count = max(grouped) if grouped else 1
    faces: list[PaperPage] = []
    for page_no in sorted(grouped):
        group = grouped[page_no]
        slots = tuple(_slot(paper.slots_per_page, item) for item in group)
        first = group[0]
        faces.append(
            PaperPage(
                question_version_id=first.question_version_id,
                answer_version_id=first.answer_version_id,
                formula="",
                student_id=paper.student_id,
                page_number=page_no,
                item_order=paper.item_order,
                asset_ids=paper.asset_ids,
                layout_template_id=paper.layout_template_id,
                paper_id=paper.paper_id,
                page_count=count,
                printed_external_id=paper.printed_external_id,
                qr_printed=paper.qr_printed,
                stem=first.stem_text,
                slots=slots,
            )
        )
    return tuple(faces)


def _slot(slots_per_page: int, item: PracticeItem) -> SlotFace:
    options = tuple(line for line in item.option_text.split("\n") if line)
    return SlotFace(
        order_no=item.order_no,
        slot_no=item.slot_no,
        slot_span=item.slot_span,
        stem=item.stem_text,
        options=options,
        answer_box=slot_answer_box(slots_per_page, item.slot_no, item.slot_span),
    )


def _face(paper: Paper, item: PracticeItem, count: int) -> PaperPage:
    formula = formula_from_stem(item.stem_text) if item.stem_text else paper.formula
    return PaperPage(
        question_version_id=item.question_version_id,
        answer_version_id=item.answer_version_id,
        formula=formula,
        student_id=paper.student_id,
        page_number=item.order_no,
        item_order=paper.item_order,
        asset_ids=paper.asset_ids,
        layout_template_id=paper.layout_template_id,
        paper_id=paper.paper_id,
        page_count=count,
        printed_external_id=paper.printed_external_id,
        qr_printed=paper.qr_printed,
        stem=item.stem_text,
    )


def _load_allowed(
    paper_id: str,
    auth: Authorizer,
    store: PracticeStore,
    logger: Logger,
    request_id: str,
    started: float,
    actor_teacher_id: str,
) -> Ok[Paper] | Err:
    loaded = read_store(
        lambda: store.get_paper(paper_id),
        logger,
        request_id,
        "practice.render",
        started,
    )
    if isinstance(loaded, Err):
        return loaded
    paper = loaded.value
    if paper is None:
        return _refuse(logger, request_id, started, "not_found", "the paper does not exist")
    if paper.teacher_id != actor_teacher_id or not auth.allow(
        actor_teacher_id, paper.student_id, paper.subject_id
    ):
        return _refuse(logger, request_id, started, "unauthorized", "this teacher cannot handle that paper")
    return Ok(paper)


def _refuse(logger: Logger, request_id: str, started: float, code: str, message: str) -> Err:
    emit(
        logger,
        level="WARN",
        event="use_case_refused",
        request_id=request_id,
        module="practice.render",
        outcome=code,
        started=started,
    )
    return Err(code, message)
