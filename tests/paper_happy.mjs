/** AC-02 / AC-04: issue one paper, turn to another, then confirm that page. */

import { createPaperActions } from "../apps/web/src/paper_loop.js";
import { createPaperStore, initialPaperState } from "../apps/web/src/paper_state.js";

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
  return { call, nextCall };
}

function fail(detail) {
  console.error("FAIL " + detail);
  process.exit(1);
}

function attemptFor(paperId) {
  return {
    paper_id: paperId,
    answer_text: "学生写下了 5",
    sub_question_id: "sq-1",
    review_version_id: "rev-1",
    fixture_answer_id: "fixture-answer-" + paperId,
  };
}

const session = {
  actor_teacher_id: "teacher-synth",
  student_ids: ["student-synth"],
  question_version_id: "q-v1",
};
const item = {
  subject_id: "math",
  question_version_id: "q-v1",
  question_approved: true,
  answer_approved: true,
  retired: false,
  stem: "2+2",
  answer_text: "4",
};

async function happyPath() {
  const calls = queue();
  const bag = createPaperStore({
    ...initialPaperState,
    session,
    item,
  });
  const actions = createPaperActions({
    call: calls.call,
    reviewVersionId: "rev-1",
    get: bag.get,
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

  const issued = actions.issue();
  const post = await calls.nextCall();
  if (post.path !== "/api/practice/papers" || post.options.method !== "POST") fail(post.path);
  post.resolve({ paper_id: "A", status: "可打印", student_id: "student-synth", file_id: "file-a" });
  const attemptA = await calls.nextCall();
  if (attemptA.path !== "/api/practice/papers/A/attempt") fail(attemptA.path);
  attemptA.resolve(attemptFor("A"));
  const list = await calls.nextCall();
  if (list.path !== "/api/practice/papers") fail(list.path);
  list.resolve({
    papers: [
      { paper_id: "A", status: "可打印", student_id: "student-synth", file_id: "file-a" },
      { paper_id: "B", status: "可打印", student_id: "student-synth", file_id: "file-b" },
    ],
  });
  await issued;
  if (bag.get().paper.paper_id !== "A") fail("issue did not open A");

  const turned = actions.choosePaper({
    paper_id: "B",
    status: "可打印",
    student_id: "student-synth",
    file_id: "file-b",
  });
  const attemptB = await calls.nextCall();
  if (attemptB.path !== "/api/practice/papers/B/attempt") fail(attemptB.path);
  attemptB.resolve(attemptFor("B"));
  await turned;
  if (bag.get().paper.paper_id !== "B" || bag.get().attempt.fixture_answer_id !== "fixture-answer-B") {
    fail("turn did not open B");
  }

  const confirming = actions.confirm();
  const confirmCall = await calls.nextCall();
  const sent = JSON.parse(confirmCall.options.body);
  if (sent.paper_id !== "B" || sent.fixture_answer_id !== "fixture-answer-B" || sent.operation_key !== "key-web-1") {
    fail(JSON.stringify(sent));
  }
  confirmCall.resolve({ confirmation_id: "conf-b", count: 1 });
  await confirming;
  if (bag.get().confirmation.confirmation_id !== "conf-b" || bag.get().confirmation.count !== 1) {
    fail("confirm");
  }
  if (bag.get().error || bag.get().errorCode) fail(bag.get().error);
  console.log("HAPPY issue=A turn=B confirm=conf-b");
}

happyPath().then(
  () => console.log("HAPPY PASS"),
  (reason) => fail(reason && reason.stack ? reason.stack : String(reason)),
);
