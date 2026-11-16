/** Deterministic overlap: A's hand-out settles, then B's older paper list arrives. */

import { createPaperActions } from "../apps/web/src/paper_loop.js";

function queue() {
  const waits = [];
  let notify = null;
  function call(path, options) {
    return new Promise((resolve, reject) => {
      waits.push({ path, options, resolve, reject });
      if (notify) {
        const wake = notify;
        notify = null;
        wake();
      }
    });
  }
  function nextCall() {
    if (waits.length) return Promise.resolve(waits.shift());
    return new Promise((resolve) => {
      notify = () => resolve(waits.shift());
    });
  }
  return { call, nextCall, pending: () => waits.length };
}

function store(initial) {
  const state = { ...initial, papers: initial.papers.map((row) => ({ ...row })) };
  function set(name) {
    return (value) => {
      state[name] = typeof value === "function" ? value(state[name]) : value;
    };
  }
  return { state, set };
}

function fail(code, detail) {
  console.error("FAIL " + code + " " + detail);
  process.exit(code);
}

function actionsFor(bag, calls) {
  return createPaperActions({
    call: calls.call,
    reviewVersionId: "rev-1",
    get: () => bag.state,
    setSession: bag.set("session"),
    setItem: bag.set("item"),
    setStudentId: bag.set("studentId"),
    setPaper: bag.set("paper"),
    setPapers: bag.set("papers"),
    setAttempt: bag.set("attempt"),
    setConfirmation: bag.set("confirmation"),
    setSavedPayload: bag.set("savedPayload"),
    setMessage: bag.set("message"),
    setError: bag.set("error"),
    setErrorCode: bag.set("errorCode"),
    setIssuing: bag.set("issuing"),
  });
}

const session = {
  actor_teacher_id: "teacher-synth",
  student_ids: ["student-synth", "student-synth-2"],
  question_version_id: "q-v1",
};
const item = {
  subject_id: "math",
  question_version_id: "q-v1",
  question_approved: true,
  answer_approved: true,
  retired: false,
};

function attemptFor(paperId) {
  return {
    paper_id: paperId,
    answer_text: "学生写下了 5",
    sub_question_id: "sq-1",
    review_version_id: "rev-1",
    fixture_answer_id: "fixture-answer-" + paperId,
  };
}

async function staleListKeepsHandOut() {
  const calls = queue();
  const bag = store({
    session,
    item,
    studentId: "student-synth-2",
    paper: { paper_id: "A", status: "可打印", student_id: "student-synth" },
    papers: [
      { paper_id: "A", status: "可打印", student_id: "student-synth" },
      { paper_id: "C", status: "可打印", student_id: "student-synth-3", file_id: "file-old" },
      { paper_id: "Z", status: "已发放", student_id: "student-synth-9" },
    ],
    attempt: attemptFor("A"),
    confirmation: null,
    savedPayload: null,
    message: "",
    error: "",
    errorCode: "",
    issuing: false,
    decision: "adopt",
    operationKey: "key-b",
  });
  const actions = actionsFor(bag, calls);
  const hand = actions.handOut();
  const handCall = await calls.nextCall();
  if (handCall.path !== "/api/practice/papers/A/handout") fail(2, handCall.path);

  const issued = actions.issue();
  const post = await calls.nextCall();
  if (post.path !== "/api/practice/papers" || post.options.method !== "POST") fail(3, post.path);
  if (!bag.state.issuing) fail(4, "issuing");
  const blocked = calls.pending();
  actions.handOut();
  actions.confirm();
  if (calls.pending() !== blocked) fail(5, "issued a hand-out or confirm while issuing");

  post.resolve({ paper_id: "B", status: "可打印", student_id: "student-synth-2" });
  const attemptCall = await calls.nextCall();
  if (attemptCall.path !== "/api/practice/papers/B/attempt") fail(6, attemptCall.path);
  attemptCall.resolve(attemptFor("B"));
  const listCall = await calls.nextCall();
  if (listCall.path !== "/api/practice/papers") fail(7, listCall.path);
  if (!bag.state.issuing || bag.state.paper.paper_id !== "B") fail(8, "B was not open before the list");
  if (bag.state.attempt.fixture_answer_id !== "fixture-answer-B") fail(9, "attempt");
  const stillBlocked = calls.pending();
  actions.handOut();
  actions.confirm();
  if (calls.pending() !== stillBlocked) fail(10, "old paper was handed out or confirmed during issue");

  handCall.resolve({ paper_id: "A", status: "已发放", student_id: "student-synth" });
  await hand;
  const patched = bag.state.papers.find((row) => row.paper_id === "A");
  if (!patched || patched.status !== "已发放") fail(11, "patch " + JSON.stringify(bag.state.papers));

  listCall.resolve({
    papers: [
      { paper_id: "A", status: "可打印", student_id: "student-synth" },
      { paper_id: "B", status: "可打印", student_id: "student-synth-2", file_id: "file-b" },
      { paper_id: "C", status: "可打印", student_id: "student-synth-3", file_id: "file-new" },
    ],
  });
  await issued;
  const rowA = bag.state.papers.find((row) => row.paper_id === "A");
  if (!rowA || rowA.status !== "已发放") fail(12, "A reverted " + JSON.stringify(bag.state.papers));
  if (bag.state.papers.some((row) => row.paper_id === "Z")) fail(13, "dropped paper returned");
  const rowB = bag.state.papers.find((row) => row.paper_id === "B");
  const rowC = bag.state.papers.find((row) => row.paper_id === "C");
  if (!rowB || rowB.file_id !== "file-b" || rowB.status !== "可打印") fail(14, "B list");
  if (!rowC || rowC.file_id !== "file-new") fail(15, "C list");
  if (bag.state.paper.paper_id !== "B" || bag.state.paper.student_id !== "student-synth-2") fail(16, "open paper");
  if (bag.state.attempt.paper_id !== "B" || bag.state.attempt.fixture_answer_id !== "fixture-answer-B") {
    fail(17, "open attempt");
  }
  if (bag.state.error || bag.state.errorCode) fail(18, bag.state.error);

  const confirming = actions.confirm();
  const confirmCall = await calls.nextCall();
  const sent = JSON.parse(confirmCall.options.body);
  if (sent.paper_id !== "B" || sent.fixture_answer_id !== "fixture-answer-B" || sent.operation_key !== "key-b") {
    fail(19, JSON.stringify(sent));
  }
  confirmCall.resolve({ confirmation_id: "conf-B", count: 1 });
  await confirming;
  bag.state.operationKey = "key-edited";
  bag.state.decision = "reject";
  const retrying = actions.retry();
  const retryCall = await calls.nextCall();
  const again = JSON.parse(retryCall.options.body);
  if (again.operation_key !== "key-b" || again.paper_id !== "B" || again.fixture_answer_id !== "fixture-answer-B") {
    fail(20, JSON.stringify(again));
  }
  retryCall.resolve({ confirmation_id: "conf-B", count: 1 });
  await retrying;
  if (bag.state.confirmation.confirmation_id !== "conf-B") fail(21, "confirmation");
  console.log("LIST RACE A=已发放 open=B attempt=fixture-answer-B confirm=B retry=key-b");
}

async function lateHandOutErrorStaysOffB() {
  const calls = queue();
  const bag = store({
    session,
    item,
    studentId: "student-synth-2",
    paper: { paper_id: "A", status: "可打印", student_id: "student-synth" },
    papers: [{ paper_id: "A", status: "可打印", student_id: "student-synth" }],
    attempt: attemptFor("A"),
    confirmation: null,
    savedPayload: null,
    message: "已打开卷 A",
    error: "",
    errorCode: "",
    issuing: false,
    decision: "adopt",
    operationKey: "key-b",
  });
  const actions = actionsFor(bag, calls);
  const hand = actions.handOut();
  const handCall = await calls.nextCall();
  const issued = actions.issue();
  const post = await calls.nextCall();
  post.resolve({ paper_id: "B", status: "可打印", student_id: "student-synth-2" });
  const attemptCall = await calls.nextCall();
  attemptCall.resolve(attemptFor("B"));
  const listCall = await calls.nextCall();
  listCall.resolve({
    papers: [
      { paper_id: "A", status: "可打印", student_id: "student-synth" },
      { paper_id: "B", status: "可打印", student_id: "student-synth-2" },
    ],
  });
  await issued;
  handCall.reject({ code: "retired", message: "publication is retired" });
  await hand;
  if (bag.state.error || bag.state.errorCode) fail(22, bag.state.errorCode + " " + bag.state.error);
  if (bag.state.paper.paper_id !== "B" || bag.state.attempt.fixture_answer_id !== "fixture-answer-B") {
    fail(23, "late error moved the open paper");
  }
  console.log("LIST RACE late-error paper=B attempt=fixture-answer-B error=");
}

await staleListKeepsHandOut();
await lateHandOutErrorStaysOffB();
console.log("LIST RACE PASS");
