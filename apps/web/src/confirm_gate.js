/** Switch, load, and same-key retry rules for the confirm section. */

export function startSwitch(generation) {
  return generation + 1;
}

export function cleared() {
  return {
    attempt: null,
    confirmation: null,
    payload: null,
    confirmAllowed: false,
  };
}

export function acceptLoad(requestedGeneration, currentGeneration, attempt) {
  if (requestedGeneration !== currentGeneration) {
    return { apply: false, attempt: null, confirmAllowed: false };
  }
  if (attempt == null) {
    return { apply: true, attempt: null, confirmAllowed: false };
  }
  return { apply: true, attempt, confirmAllowed: true };
}

export function acceptResponse(requestedGeneration, currentGeneration, body) {
  if (requestedGeneration !== currentGeneration) {
    return { apply: false, body: null };
  }
  return { apply: true, body };
}

export function takeHandOut(view, token, currentGeneration, outcome) {
  if (token !== currentGeneration) {
    return { apply: false, view };
  }
  if (outcome.error) {
    const code = outcome.error.code || "";
    const text = outcome.error.message || "";
    return {
      apply: true,
      view: {
        ...view,
        message: "",
        errorCode: code,
        error: code ? code + "：" + text : text,
      },
    };
  }
  return {
    apply: true,
    view: {
      ...view,
      paper: { ...view.paper, ...outcome.paper },
      message: "已发放",
      error: "",
      errorCode: "",
    },
  };
}

export function confirmPayload(paper, attempt, teacherId, decision, operationKey) {
  return {
    operation_key: operationKey,
    paper_id: paper.paper_id,
    sub_question_id: attempt.sub_question_id,
    teacher_id: teacherId,
    review_version_id: attempt.review_version_id,
    decision,
    fixture_answer_id: attempt.fixture_answer_id,
  };
}

export function attemptBlock(errorCode) {
  if (errorCode !== "attempt_not_current") {
    return null;
  }
  return {
    confirmAllowed: false,
    notice: "当前无法确认。这一版复核还没有作答。",
    nextStep: "重新打开这张卷",
  };
}

export function retryBody(storedPayload, _editedPayload) {
  return storedPayload;
}

export function showConflictReload(errorCode) {
  return errorCode === "version_mismatch";
}
