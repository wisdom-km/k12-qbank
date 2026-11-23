/** Issue, hand-out, and confirm actions shared by the page and the overlap test. */

import {
  acceptLoad,
  acceptResponse,
  canHandOut,
  cleared,
  confirmPayload,
  confirmReady,
  patchHandOutList,
  retryBody,
  startSwitch,
  takeHandOut,
} from "./confirm_gate.js";

export function createPaperActions(io) {
  const generation = { current: 0 };
  const paperNow = { current: null };
  const issuingNow = { current: false };
  const handed = new Set();

  function rememberPaper(next) {
    paperNow.current = next;
    io.setPaper(next);
  }

  function setIssuing(value) {
    issuingNow.current = value;
    io.setIssuing(value);
  }

  function beginSwitch() {
    const token = startSwitch(generation.current);
    generation.current = token;
    const blank = cleared();
    setIssuing(false);
    io.setAttempt(blank.attempt);
    io.setConfirmation(blank.confirmation);
    io.setSavedPayload(blank.payload);
    return token;
  }

  async function run(action) {
    io.setError("");
    io.setErrorCode("");
    io.setMessage("");
    try {
      await action();
    } catch (reason) {
      const code = (reason && reason.code) || "";
      const text = (reason && reason.message) || "";
      io.setErrorCode(code);
      io.setError(code ? code + "：" + text : text);
    }
  }

  function noteHanded(paper) {
    if (paper && paper.paper_id && paper.status === "已发放") handed.add(paper.paper_id);
  }

  function writePapers(incoming) {
    io.setPapers((rows) => {
      const keep = new Set(handed);
      for (const row of rows || []) {
        if (row && row.paper_id && row.status === "已发放") keep.add(row.paper_id);
      }
      return (incoming || []).map((row) => (row && keep.has(row.paper_id) ? { ...row, status: "已发放" } : row));
    });
  }

  async function load() {
    const nextSession = await io.call("/api/session");
    const listed = await io.call("/api/catalog");
    const items = listed && listed.items ? listed.items : [];
    const preferred = pickQuestion(items, nextSession.question_version_id);
    const nextItem = await io.call("/api/catalog/" + preferred);
    const nextPapers = await io.call("/api/practice/papers");
    io.setSession(nextSession);
    if (io.setItems) io.setItems(items);
    io.setItem(nextItem);
    writePapers(nextPapers.papers);
    const studentId = io.get().studentId;
    if (!nextSession.student_ids.includes(studentId) && nextSession.student_ids[0]) {
      io.setStudentId(nextSession.student_ids[0]);
    }
  }

  function issue() {
    const token = beginSwitch();
    setIssuing(true);
    return run(async () => {
      const snap = io.get();
      try {
        const opened = await io.call("/api/practice/papers", {
          method: "POST",
          body: JSON.stringify({
            teacher_id: snap.session.actor_teacher_id,
            student_id: snap.studentId,
            subject_id: snap.item.subject_id,
            question_version_id: snap.item.question_version_id,
            review_version_id: io.reviewVersionId,
          }),
        });
        const posted = acceptResponse(token, generation.current, opened);
        if (!posted.apply || !posted.body) return;
        rememberPaper(posted.body);
        const nextAttempt = await io.call("/api/practice/papers/" + posted.body.paper_id + "/attempt");
        const applied = acceptLoad(token, generation.current, nextAttempt);
        if (applied.apply) io.setAttempt(applied.attempt);
        const nextPapers = await io.call("/api/practice/papers");
        const listed = acceptResponse(token, generation.current, nextPapers);
        if (!listed.apply || !listed.body) return;
        writePapers(listed.body.papers);
        io.setMessage(posted.body.status === "可打印" ? "已出卷，可以打开 PDF" : "已出卷，仍待渲染");
      } finally {
        if (generation.current === token) setIssuing(false);
      }
    });
  }

  function handOut() {
    const snap = io.get();
    if (!canHandOut(snap.paper, issuingNow.current)) return;
    const token = generation.current;
    const source = snap.paper;
    const view = {
      paper: source,
      attempt: snap.attempt,
      confirmation: snap.confirmation,
      payload: snap.savedPayload,
      message: snap.message,
      error: snap.error,
      errorCode: snap.errorCode,
    };
    const liveId = () => (paperNow.current ? paperNow.current.paper_id : "");
    return run(async () => {
      try {
        const next = await io.call("/api/practice/papers/" + source.paper_id + "/handout", {
          method: "POST",
          body: "{}",
        });
        const taken = takeHandOut(view, token, generation.current, { paper: next }, liveId());
        if (!taken.apply) {
          noteHanded(next);
          io.setPapers((rows) => patchHandOutList(rows, next));
          return;
        }
        rememberPaper(taken.view.paper);
        noteHanded(taken.view.paper);
        const nextPapers = await io.call("/api/practice/papers");
        const listed = acceptResponse(token, generation.current, nextPapers);
        if (!listed.apply || !listed.body) return;
        writePapers(listed.body.papers);
        io.setMessage(taken.view.message);
        io.setError("");
        io.setErrorCode("");
      } catch (reason) {
        const taken = takeHandOut(
          view,
          token,
          generation.current,
          { error: { code: reason.code || "", message: reason.message || "" } },
          liveId(),
        );
        if (!taken.apply) return;
        io.setErrorCode(taken.view.errorCode);
        io.setError(taken.view.error);
        io.setMessage("");
      }
    });
  }

  function selectQuestion(questionVersionId) {
    const token = beginSwitch();
    rememberPaper(null);
    return run(async () => {
      const nextItem = await io.call("/api/catalog/" + questionVersionId);
      const applied = acceptResponse(token, generation.current, nextItem);
      if (!applied.apply || !applied.body) return;
      io.setItem(applied.body);
      io.setMessage("已打开 " + questionVersionId);
    });
  }

  function choosePaper(row) {
    const token = beginSwitch();
    rememberPaper(row);
    return run(async () => {
      try {
        const nextAttempt = await io.call("/api/practice/papers/" + row.paper_id + "/attempt");
        const applied = acceptLoad(token, generation.current, nextAttempt);
        if (!applied.apply) return;
        io.setAttempt(applied.attempt);
        io.setMessage("已打开卷 " + row.paper_id);
      } catch (reason) {
        const applied = acceptLoad(token, generation.current, null);
        if (!applied.apply) return;
        io.setAttempt(null);
        throw reason;
      }
    });
  }

  function confirm() {
    if (issuingNow.current) return;
    const snap = io.get();
    if (!confirmReady(snap.paper, snap.attempt)) return;
    const token = generation.current;
    const payload = confirmPayload(
      snap.paper,
      snap.attempt,
      snap.session.actor_teacher_id,
      snap.decision,
      snap.operationKey,
    );
    return run(async () => {
      const result = await io.call("/api/practice/confirmations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const applied = acceptResponse(token, generation.current, { confirmation: result, payload });
      if (!applied.apply || !applied.body) return;
      io.setSavedPayload(applied.body.payload);
      io.setConfirmation(applied.body.confirmation);
      io.setMessage("确认号 " + result.confirmation_id + "，正式记录 " + result.count + " 条");
    });
  }

  function retry() {
    const snap = io.get();
    const payload = retryBody(snap.savedPayload, null);
    if (!payload) return;
    const token = generation.current;
    return run(async () => {
      const result = await io.call("/api/practice/confirmations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const applied = acceptResponse(token, generation.current, { confirmation: result, payload });
      if (!applied.apply || !applied.body) return;
      io.setConfirmation(applied.body.confirmation);
      io.setMessage("确认号 " + result.confirmation_id + "，正式记录 " + result.count + " 条");
    });
  }

  return { load, issue, handOut, choosePaper, selectQuestion, confirm, retry };
}

function pickQuestion(items, preferred) {
  const ids = items.map((row) => row && row.question_version_id).filter(Boolean);
  if (ids.includes(preferred)) return preferred;
  if (ids.length > 0) return ids[0];
  return preferred;
}
